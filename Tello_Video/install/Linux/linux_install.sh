sudo apt-get update -y

# install python 2.7
sudo apt-get install python2.7 python-pip -y
sudo pip install --upgrade pip

#switch to python2.7
sudo update-alternatives --install /usr/bin/python python /usr/bin/python2 150 
sudo update-alternatives --install /usr/bin/python python /usr/bin/python3 100

sudo apt-get update -y

# install cmake
#sudo apt-get install cmake -y
sudo pip install cmake

# install dependencies

apt-get update
apt-get install -y software-properties-common
add-apt-repository universe
apt-get update

apt-get install libboost-all-dev -y
apt-get install libavcodec-dev -y
apt-get install libswscale-dev -y
apt-get install -y python3-tk

# pull and build h264 decoder library
cd h264decoder
mkdir build
cd build
cmake .. -DCMAKE_POLICY_VERSION_MINIMUM=3.5
make

# copy source .so file to tello.py directory
cp libh264decoder.so ../../

echo 'Compilation and Installation Done!'
