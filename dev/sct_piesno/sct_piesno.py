#!/usr/bin/env python
# ----------------------------------------------------------------------------------------------------------------------
#
# Copyright (c) 2016 NeuroPoly, Polytechnique Montreal <www.neuropoly.info>
# License: see the LICENSE.TXT
# ======================================================================================================================

# PIESNO makes an important assumption: the Gaussian noise standard deviation is assumed to be uniform.
# The noise is uniform across multiple slice locations or across multiple images of the same location.

import sys
import nibabel as nib
import numpy as np
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
        self.receiver_channels = 4

def main(fname_in, receiver_channels):

    img = nib.load(fname_in)
    path_input, file_input, ext_input = sct.extract_fname(fname_in)
    data = img.get_data()

    sigma, mask = piesno(data, N=receiver_channels, return_mask=True)

    sct.printv('\nWrite NIFTI volumes...')
    output_name = file_input+'_mask_piesno'+ext_input
    nib.save(nib.Nifti1Image(mask, img.get_affine(), img.get_header()), output_name)

    sct.printv('\n.. The noise standard deviation is sigma= ' + str(sigma))
    print '\n.. The std of the background is =', str(np.std(data[mask[...,None].astype(np.bool)]))

def get_parser():
    """
    :return: Returns the parser with the command line documentation contained in it.
    """
    param = Param()

    # Initialize the parser
    parser = Parser(__file__)
    parser.usage.set_description('''This program reads one images, one with acquisition information.''')
    parser.add_option(name='-i',
                      type_value='image_nifti',
                      description='Image to analyse.',
                      mandatory=True,
                      example='data_highQ.nii')
    parser.add_option(name='-n',
                      type_value='int',
                      description='number of receiver channels',
                      mandatory=True,
                      default_value=str(param.receiver_channels),
                      example='4')
    parser.usage.addSection('General options')
    return parser

if __name__ == '__main__':
    parser = get_parser()
    arguments = parser.parse(sys.argv[1:])

    fname_in = arguments['-i']
    receiver_channels = int(arguments['-n'])

    main(fname_in, receiver_channels)




