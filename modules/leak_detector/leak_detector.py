from slips_files.common.abstracts import Module
import multiprocessing
from slips_files.core.database.database import __database__
from slips_files.common.slips_utils import utils
import sys
import base64
import time
import binascii
import os
import subprocess
import json
import traceback


class Module(Module, multiprocessing.Process):
    # Name: short name of the module. Do not use spaces
    name = 'Leak Detector'
    description = 'Detect leaks of data in the traffic'
    authors = ['Alya Gomaa']

    def __init__(self, outputqueue, redis_port):
        multiprocessing.Process.__init__(self)
        self.outputqueue = outputqueue
        __database__.start(redis_port)
        # this module is only loaded when a pcap is given get the pcap path
        try:
            self.pcap = utils.sanitize(sys.argv[sys.argv.index('-f') + 1])
        except ValueError:
            # this error is raised when we start this module in the unit tests so there's no argv
            # ignore it
            pass
        self.yara_rules_path = 'modules/leak_detector/yara_rules/rules/'
        self.compiled_yara_rules_path = (
            'modules/leak_detector/yara_rules/compiled/'
        )
        self.bin_found = False
        if self.is_yara_installed():
            self.bin_found = True


    def is_yara_installed(self) -> bool:
        """
        Checks if notify-send bin is installed
        """
        cmd = 'yara -h > /dev/null 2>&1'
        returncode = os.system(cmd)
        if returncode == 256 or returncode == 0:
            # it is installed
            return True
        # elif returncode == 32512:
        self.print(f"yara is not installed. install it using:\nsudo apt-get install yara")
        return False

    def shutdown_gracefully(self):
        # Confirm that the module is done processing
        __database__.publish('finished_modules', self.name)

    def print(self, text, verbose=1, debug=0):
        """
        Function to use to print text using the outputqueue of slips.
        Slips then decides how, when and where to print this text by taking all the processes into account
        :param verbose:
            0 - don't print
            1 - basic operation/proof of work
            2 - log I/O operations and filenames
            3 - log database/profile/timewindow changes
        :param debug:
            0 - don't print
            1 - print exceptions
            2 - unsupported and unhandled types (cases that may cause errors)
            3 - red warnings that needs examination - developer warnings
        :param text: text to print. Can include format like 'Test {}'.format('here')
        """

        levels = f'{verbose}{debug}'
        self.outputqueue.put(f'{levels}|{self.name}|{text}')

    def fix_json_packet(self, json_packet):
        """
        in very large pcaps, tshark gets killed before it's done processing,
        but the first packet info is printed in a corrupted json format
        this function fixes the printed packet
        """
        json_packet = json_packet.replace("Killed", '')
        json_packet += '}]'
        try:
            return json.loads(json_packet)
        except json.decoder.JSONDecodeError:
            return False

    def get_packet_info(self, offset: int):
        """
        Parse pcap and determine the packet at this offset
        returns  a tuple with packet info (srcip, dstip, proto, sport, dport, ts) or False if not found
        """
        offset = int(offset)
        with open(self.pcap, 'rb') as f:
            # every pcap header is 24 bytes
            f.read(24)
            packet_number = 0

            packet_data_length = True
            while packet_data_length:
                # the number of the packet we're currently working with,
                # since packets start from 1 in tshark , the first packet should be 1
                packet_number += 1
                # this offset is exactly when the packet starts
                start_offset = f.tell() + 1
                # get the Packet header, every packet header is exactly 16 bytes long
                packet_header = f.read(16)
                # get the length of the Packet Data field (the second last 4 bytes of the header), [::-1] for little endian
                packet_data_length = packet_header[8:12][::-1]
                # convert the hex into decimal
                packet_length_in_decimal = int.from_bytes(
                    packet_data_length, 'big'
                )

                # read until the end of this packet
                f.read(packet_length_in_decimal)
                # this offset is exactly when the packet ends
                end_offset = f.tell()
                if offset <= end_offset and offset >= start_offset:
                    # print(f"Found a match. Packet number in wireshark: {packet_number+1}")
                    # use tshark to get packet info
                    cmd = f'tshark -r "{self.pcap}" -T json -Y frame.number=={packet_number}'
                    tshark_proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        stdin=subprocess.PIPE,
                        shell=True
                    )

                    result, error = tshark_proc.communicate()
                    if error:
                        self.print (f"tshark error {tshark_proc.returncode}: {error.strip()}")
                        return

                    json_packet = result.decode()

                    try:
                        json_packet = json.loads(json_packet)
                    except json.decoder.JSONDecodeError:
                        json_packet = self.fix_json_packet(json_packet)

                    if json_packet:
                        # sometime tshark can't find the desired packet?
                        json_packet = json_packet[0]['_source']['layers']

                        # get ip family and used protocol
                        used_protocols = json_packet['frame'][
                            'frame.protocols'
                        ]
                        ip_family = 'ipv6' if 'ipv6' in used_protocols else 'ip'
                        if 'tcp' in used_protocols:
                            proto = 'tcp'
                        elif 'udp' in used_protocols:
                            proto = 'udp'
                        else:
                            # probably ipv6.hopopt
                            return

                        try:
                            ts = json_packet['frame']['frame.time_epoch']
                            srcip = json_packet[ip_family][f'{ip_family}.src']
                            dstip = json_packet[ip_family][f'{ip_family}.dst']
                            sport = json_packet[proto][f'{proto}.srcport']
                            dport = json_packet[proto][f'{proto}.dstport']
                        except KeyError:
                            return

                        return (srcip, dstip, proto, sport, dport, ts)

        return False

    def set_evidence_yara_match(self, info: dict):
        """
        This function is called when yara finds a match
        :param info: a dict with info about the matched rule, example keys 'vars_matched', 'index',
        'rule', 'srings_matched'
        """
        rule = info.get('rule').replace('_', ' ')
        offset = info.get('offset')
        # vars_matched = info.get('vars_matched')
        strings_matched = info.get('strings_matched')
        # we now know there's a match at offset x, we need to know offset x belongs to which packet
        if packet_info := self.get_packet_info(offset):
            srcip, dstip, proto, sport, dport, ts = (
                packet_info[0],
                packet_info[1],
                packet_info[2],
                packet_info[3],
                packet_info[4],
                packet_info[5],
            )

            portproto = f'{dport}/{proto}'
            port_info = __database__.get_port_info(portproto)

            # generate a random uid
            uid = base64.b64encode(binascii.b2a_hex(os.urandom(9))).decode(
                'utf-8'
            )
            src_profileid = f'profile_{srcip}'
            dst_profileid = f'profile_{dstip}'
            # sometimes this module tries to find the profile before it's created. so
            # wait a while before alerting.
            time.sleep(4)
            # make sure we have a profile for any of the above IPs
            if __database__.has_profile(src_profileid):
                attacker_direction = 'dstip'
                profileid = src_profileid
                attacker = dstip
                ip_identification = __database__.getIPIdentification(dstip)
                description = (
                    f'{rule} to destination address: {dstip} {ip_identification} '
                    f"port: {portproto} {port_info if port_info else ''}. Leaked location: {strings_matched}"
                )

            elif __database__.has_profile(dst_profileid):
                attacker_direction = 'srcip'
                profileid = dst_profileid
                attacker = srcip
                ip_identification = __database__.getIPIdentification(srcip)
                description = (
                    f'{rule} to destination address: {srcip} {ip_identification} '
                    f"port: {portproto} {port_info if port_info else ''}. Leaked location: {strings_matched}"
                )

            else:
                # no profiles in slips for either IPs
                return

            # in which tw is this ts?
            twid = __database__.getTWofTime(profileid, ts)
            # convert ts to a readable format
            ts = utils.convert_format(ts, utils.alerts_format)
            if twid:
                twid = twid[0]
                source_target_tag = 'CC'
                # TODO: this needs to be changed if add more rules to the rules/dir
                evidence_type = 'NETWORK_gps_location_leaked'
                category = 'Malware'
                confidence = 0.9
                threat_level = 'high'
                __database__.setEvidence(evidence_type, attacker_direction, attacker, threat_level, confidence,
                                         description, ts, category, source_target_tag=source_target_tag, port=dport,
                                         proto=proto, profileid=profileid, twid=twid, uid=uid)

    def compile_and_save_rules(self):
        """
        Compile and save all yara rules in the compiled_yara_rules_path
        """

        try:
            os.mkdir(self.compiled_yara_rules_path)
        except FileExistsError:
            pass

        for yara_rule in os.listdir(self.yara_rules_path):
            compiled_rule_path = os.path.join(
                self.compiled_yara_rules_path, f'{yara_rule}_compiled'
            )
            # if we already have the rule compiled, don't compile again
            if os.path.exists(compiled_rule_path):
                # we already have the rule compiled
                continue

            # get the complete path of the .yara rule
            rule_path = os.path.join(self.yara_rules_path, yara_rule)
            # compile
            cmd = f'yarac {rule_path} {compiled_rule_path} >/dev/null 2>&1'
            return_code = os.system(cmd)
            if return_code != 0:
                self.print(f"Error compiling {yara_rule}.")
                return False
        return True


    def find_matches(self):
        """Run yara rules on the given pcap and find matches"""
        for compiled_rule in os.listdir(self.compiled_yara_rules_path):
            compiled_rule_path = os.path.join(self.compiled_yara_rules_path, compiled_rule)
            # -p 7 means use 7 threads for faster analysis
            # -f to stop searching for strings when they were already found
            # -s prints the found string
            cmd = f'yara -C {compiled_rule_path} "{self.pcap}" -p 7 -f -s '
            yara_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                shell=True
            )

            lines, error = yara_proc.communicate()
            lines = lines.decode()
            if error:
                self.print (f"YARA error {yara_proc.returncode}: {error.strip()}")
                return
            if not lines:
                # no match
                return

            lines = lines.splitlines()
            matching_rule = lines[0].split()[0]
            # each match (line) should be a separate detection(yara match)
            for line in lines[1:]:
                # example of a line: 0x4e15c:$rgx_gps_loc: ll=00.000000,-00.000000
                line = line.split(':')
                # offset: pcap index where the rule was matched
                offset = int(line[0], 16)
                # var is either $rgx_gps_loc, $rgx_gps_lon or $rgx_gps_lat
                var = line[1].replace('$', '')
                # strings_matched is exactly the string that was found that triggered this detection
                # starts from the var until the end of the line
                strings_matched = ' '.join([s for s in line[2:]])
                self.set_evidence_yara_match({
                    'rule': matching_rule,
                    'vars_matched': var,
                    'strings_matched': strings_matched,
                    'offset': offset,
                })

    def run(self):
        utils.drop_root_privs()
        try:
            if not self.bin_found:
                return True

            # if we we don't have compiled rules, compile them
            if self.compile_and_save_rules():
                # run the yara rules on the given pcap
                self.find_matches()
        except KeyboardInterrupt:
            self.shutdown_gracefully()
            return True
        except Exception as inst:
            exception_line = sys.exc_info()[2].tb_lineno
            self.print(f'Problem on the run() line {exception_line}', 0, 1)
            self.print(traceback.format_exc(), 0, 1)
            return True
