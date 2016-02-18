#!/usr/bin/env python
# ==========================================================================================
#
# Copyright (c) 2016 NeuroPoly, Polytechnique Montreal <www.neuro.polymtl.ca>
# Authors: Tanguy Duval, Charley Gros
#
# License: see the LICENSE.TXT
# ==========================================================================================

import sys
import numpy as np
import nibabel as nib
import sct_utils as sct
from msct_parser import Parser
from dipy.denoise.noise_estimate import piesno

try:
    import nibabel as nib
except ImportError:
    print '--- nibabel not installed! Exit program. ---'
    sys.exit(2)
try:
    import numpy as np
except ImportError:
    print '--- numpy not installed! Exit program. ---'
    sys.exit(2)

class Param:
    def __init__(self):
        self.freedom_degree = 1

def main(fname_in, freedom_degree,folder_output):

    img = nib.load(fname_in)
    path_fname, file_fname, ext_fname = sct.extract_fname(fname_in)
    data = img.get_data()

    sigma, mask = piesno(data, N=freedom_degree, return_mask=True)

    sct.printv('\nWrite NIFTI volumes...')
    output_name = file_fname+'_noise_mask'+ext_fname
    if folder_output == ".":
        output_name = output_name
    else:
        output_name = folder_output+"/"+output_name
    nib.save(nib.Nifti1Image(mask, img.get_affine(), img.get_header()), output_name)
    sct.printv('\n.. The noise standard deviation is sigma = ' + str(sigma))

def get_parser():

    """
    :return: Returns the parser with the command line documentation contained in it.
    """
    param = Param()

    # Initialize the parser
    parser = Parser(__file__)
    parser.usage.set_description('''Identification and estimation of noise in the diffusion signal, implemented by the Dipy software project (http://nipy.org/dipy/), based on the PIESNO method: Koay C.G., E. Ozarslan, C. Pierpaoli. Probabilistic Identification and Estimation of Noise (PIESNO): A self-consistent approach and its applications in MRI. JMR, 199(1):94-103, 2009.''')
    parser.add_option(name='-i',
                      type_value='image_nifti',
                      description='Input data',
                      mandatory=True,
                      example='data_highQ.nii')
    parser.add_option(name='-dof',
                      type_value='int',
                      description='Degree of freedom of the noise distribution. Corresponds to the number of antenna for an acquisition without parallel imaging with sum of squares combination. Otherwise, dof is close to 1.',
                      mandatory=False,
                      default_value=str(param.freedom_degree),
                      example='1')
    parser.add_option(name='-ofolder',
                      type_value='output_folder',
                      description='Output folder',
                      mandatory=False,
                      example='My_Output_Folder/',
                      default_value='')
    parser.usage.addSection('General options')
    parser.add_option(name='-h',
                      type_value=None,
                      description='Display this help.',
                      mandatory=False)
    return parser

if __name__ == '__main__':
    parser = get_parser()
    arguments = parser.parse(sys.argv[1:])

    fname_in = arguments['-i']
    freedom_degree = int(arguments['-dof'])

    if "-ofolder" in arguments:
        folder_output = arguments["-ofolder"]
    else:
        folder_output = '.'

    main(fname_in, freedom_degree,folder_output)
