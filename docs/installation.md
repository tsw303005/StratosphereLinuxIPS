# Installation

There are two ways to install and run Slips: inside a Docker or in your own computer. We suggest to install and to run Slips inside a Docker since all dependencies are already installed in there. However, current version of docker with Slips does not allow to capture the traffic from the computer's interface. We will describe both ways of installation anyway. 

## Slips in Docker.

Slips can be run inside a Docker. There is a prepared docker image with Slips available in DockerHub and it is also possible to build a docker with Slips locally from the Dockerfile. But in both cases, you have to have the Docker platform installed in your computer. Instructions how to install Docker is https://docs.docker.com/get-docker/.

### Running Slips from DockerHub

	mkdir ~/dataset
	cp <some-place>/myfile.pcap ~/dataset
	docker run -it --rm --net=host -v ~/dataset:/StratosphereLinuxIPS/dataset stratosphereips/slips:latest
	./slips.py -c config/slips.conf -r dataset/myfile.pcap

### Running Slips using docker compose


Change enp1s0 to your current interface in docker/docker-compose.yml and start slips using
    
    docker compose -f docker/docker-compose.yml up

Now everything inside your host's ```config``` and ```dataset``` directories is
mounted to ```/StratosphereLinuxIPS/config/``` and ```/StratosphereLinuxIPS/dataset/``` in Slips docker.

To run slips on a pcap instead of your interface you can do the following:

1. put the pcap in the ```dataset/``` dir in your host
2. change the entrypoint in the docker compose file to
    ["python3","/StratosphereLinuxIPS/slips.py","-f","dataset/<pcapname>.pcap"]
3. restart slips using ```docker compose -f docker/docker-compose.yml up```


### Building Slips from the Dockerfile

Before building the docker locally from the Dockerfile, first you should clone Slips repo or download the code directly: 

	git clone https://github.com/stratosphereips/StratosphereLinuxIPS.git

If you cloned Slips in '~/code/StratosphereLinuxIPS', then you can build the Docker image with:

	cd ~/code/StratosphereLinuxIPS/docker/ubunutu-image
	docker build --no-cache -t slips -f Dockerfile .
	docker run -it --rm --net=host -v ~/code/StratosphereLinuxIPS/dataset:/StratosphereLinuxIPS/dataset slips
	./slips.py -c config/slips.conf -f dataset/test3.binetflow

If you don't have Internet connection from inside your Docker image while building, you may have another set of networks defined in your Docker. For that try:

	docker build --network=host --no-cache -t slips -f Dockerfile .
	
You can also put your own files in the /dataset/ folder and analyze them with Slips:

	cp some-pcap-file.pcap ~/code/StratosphereLinuxIPS/dataset
	docker run -it --rm --net=host -v ../dataset/:/StratosphereLinuxIPS/dataset slips
	./slips.py -c config/slips.conf -f dataset/some-pcap-file.pcap


Note that some GPUs don't support tensorflow in docker which may cause "Illegal instruction" errors when running slips.

To fix this you can disable all machine learning based modules when running Slips in docker, or run Slips locally.

## Installing Slips in your own computer.

Slips is dependent on three major elements: 

Python 3.8
Zeek
Redis database 7.0.4

To install these elements we will use APT package manager. Afterwards, we will install python packages required for Slips to run and its modules to work. Also, Slips' interface Kalipso depend on Node.JS and several npm packages. 

**Instructions to download everything for Slips are below.**
<br>

## Install using shell script
You can install it using install.sh

	sudo chmod +x install.sh
	sudo ./install.sh
	
or install it manually

## Installing manually
### Installing Python, Redis, NodeJs, and required python and npm libraries.
Update the repository of packages so you see the latest versions:

	apt-get update
	
Install the required packages (-y to install without asking for approval):

    apt-get -y installtshark iproute2 python3.8 python3-tzlocal net-tools python3-dev build-essential python3-certifi curl git gnupg ca-certificates redis wget python3-minimal python3-redis python3-pip python3-watchdog nodejs redis-server npm lsof file iptables nfdump zeek whois yara
    apt install -y --no-install-recommends nodejs
	
Even though we just installed pip3, the package installer for Python (3.8), we need to upgrade it to its latest version:

	python3 -m pip install --upgrade pip

Now that pip3 is upgraded, we can proceed to install all required packages via pip3 python packet manager:

	sudo pip3 install -r requirements.txt

_Note: for those using a different base image, you need to also install tensorflow==2.2.0 via pip3._

As we mentioned before, the GUI of Slips known as Kalipso relies on NodeJs v19. Make sure to use NodeJs greater than version 12. For Kalipso to work, we will install the following npm packages:

    curl -fsSL https://deb.nodesource.com/setup_19.x | bash - && apt install -y --no-install-recommends nodejs
    cd modules/kalipso &&  npm install

###  Installing Zeek

The last requirement to run Slips is Zeek. Zeek is not directly available on Ubuntu or Debian. To install it, we will first add the repository source to our apt package manager source list. The following two commands are for Ubuntu, check the repositories for the correct version if you are using a different OS:

	echo 'deb http://download.opensuse.org/repositories/security:/zeek/xUbuntu_18.04/ /' | tee /etc/apt/sources.list.d/security:zeek.list

We will download and store the gpg signature from the package for apt to read:

	curl -fsSL http://download.opensuse.org/repositories/security:/zeek/xUbuntu_18.04/Release.key | gpg --dearmor | tee /etc/apt/trusted.gpg.d/security_zeek.gpg > /dev/null

Finally, we will update the package manager repositories and install zeek

	apt-get update
	apt-get -y install zeek
	
To make sure that zeek can be found in the system we will add its link to a known path:

	ln -s /opt/zeek/bin/zeek /usr/local/bin

### Running Slips for the First Time


Once Redis is running it’s time to clone the Slips repository and run it:

	git clone https://github.com/stratosphereips/StratosphereLinuxIPS.git
	cd StratosphereLinuxIPS/
	./slips.py -c config/slips.conf -f dataset/hide-and-seek-short.pcap

Run slips with sudo to enable blocking (Optional) 


## Running Slips from Docker with P2P support
You can use Slips with P2P directly in a special docker image by doing:

```
docker pull stratosphereips/slips_p2p
docker run -it --rm --net=host stratosphereips/slips_p2p
```

## Build Slips in Docker with P2P support

git clone https://github.com/stratosphereips/StratosphereLinuxIPS.git

If you cloned Slips in '~/StratosphereLinuxIPS', make sufe you are in slips root directory, then you can build the Docker image with P2P installed using:

	cd ~/StratosphereLinuxIPS/
	docker build --network=host --no-cache -t slips_p2p -f docker/P2P-image/Dockerfile .
	docker run -it --rm --net=host slips_p2p

Now you can edit config/slips.conf to enable p2p. [usage instructions here](https://stratospherelinuxips.readthedocs.io/en/develop/p2p.html#usage). then run Slips using your interface:

	./slips.py -i wlp3s0

## Installing Slips on a Raspberry PI

Instead of compiling zeek, you can grab the zeek binaries for your OS

Packages for Raspbian 11:

[https://download.opensuse.org/repositories/security:/zeek/Raspbian_11/armhf/zeek_4.2.1-0_armhf.deb](https://download.opensuse.org/repositories/security:/zeek/Raspbian_11/armhf/zeek_4.2.1-0_armhf.deb)


Packages for Raspbian 10:

[https://download.opensuse.org/repositories/security:/zeek/Raspbian_10/armhf/zeek_4.2.1-0_armhf.deb](https://download.opensuse.org/repositories/security:/zeek/Raspbian_10/armhf/zeek_4.2.1-0_armhf.deb)

