#!/usr/bin/env python
#########################################################################################
# Copyright (c) 2016 Polytechnique Montreal <www.neuro.polymtl.ca>
# Authors: Charley Gros
# Modified: 2016-03-05
#
# About the license: see the file LICENSE.TXT
#########################################################################################

import os
import sys
from nipype.interfaces.ants import N4BiasFieldCorrection
from msct_parser import Parser
import sct_utils as sct


# DEFAULT PARAMETERS
#=======================================================================================================================
class Param:
    def __init__(self):
        self.fname_data = ''
        self.fname_out = 'bias_field_correction.nii.gz'
        self.fname_mask = ''
        #self.grid = '1'
        self.iter = '[ 50x50x80 ]'


# MAIN
#=======================================================================================================================
def main():

    # Check input parameters
    parser = get_parser()
    arguments = parser.parse(sys.argv[1:])

    param.fname_data = arguments['-i']

    cmd = 'N4BiasFieldCorrection --input-image ' + param.fname_data

    if '-o' in arguments:
        param.fname_out = arguments['-o']
    cmd += ' --output ' + param.fname_out
    if '-mask' in arguments:
        param.fname_mask = arguments['-mask']
        cmd += ' --mask-image ' + param.fname_mask
    #if '-grid' in arguments:
    #    param.mesh = int(arguments['-grid'])
    #cmd += ' --meshresolution ' + str(param.grid)
    if '-nbiter' in arguments:
        param.iter = arguments['-nbiter']
    cmd += ' --convergence ' + param.iter

    os.system(cmd)

    # to view results
    sct.printv('\nDone! To view results, type:', 1)
    sct.printv('fslview '+param.fname_out + ' &', 1, 'info')

# GET PARSER
#=======================================================================================================================
def get_parser():
    # Initialize the parser
    parser = Parser(__file__)
    parser.usage.set_description('Performs image bias correction using N4 algorithm. This module is based on the ITK '
                                 'filters contributed in the following publication: Tustison N, Gee J : N4ITK: Nick N3'
                                 ' ITK Implementation For MRI Bias Field Correction, The Insight Journal 2009 '
                                 'January-June, http://hdl.handle.net/10380/3053')
    parser.add_option(name='-i',
                      type_value='file',
                      description='Input image with signal inhomegeneity',
                      mandatory=True,
                      example='t2.nii.gz')
    parser.add_option(name='-mask',
                      type_value='file',
                      description='Binary mask that defines the structure of your interest',
                      mandatory=False,
                      example='mask.nii.gz')
    parser.add_option(name='-o',
                      type_value='file_output',
                      description='Result of processing',
                      mandatory=False,
                      example='bias_field_corrected.nii.gz')
    parser.add_option(name='-nbiter',
                      type_value='str',
                      description='Maximum number of iterations in each dimension',
                      mandatory=False,
                      example='[ 50x50x80 ]')
    #parser.add_option(name='-grid',
    #                  type_value='int',
    #                  description='Resolution of the initial B-Spline grid',
    #                  mandatory=False,
    #                  example='1')

    return parser

# START PROGRAM
#=======================================================================================================================
if __name__ == "__main__":
    param = Param()
    main()
