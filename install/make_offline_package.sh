#!/usr/bin/env bash
# Convenience script to creates package to be installed offline
#
# This script needs to be run in the install/ directory
#
#########################################################################################
# Copyright (c) 2016 Polytechnique Montreal <www.neuro.polymtl.ca>
# Author: PO Quirion
# License: see the file LICENSE.TXT
#########################################################################################

usage (){

echo $0 the_name_of_the_distro_package

}

start_wd=$PWD

finish (){
#  Force a clean exit
  # Get back to starting point
  cd $start_wd
}
trap finish EXIT


package_name=${1}

cd ..
mkdir tmp
./install_sct <<STDIN
no
${PWD}/tmp/${package_name}
no
STDIN

cp install_sct tmp/${package_name}/.

cd tmp

tar -zcvf ${package_name}.tgz package_name








