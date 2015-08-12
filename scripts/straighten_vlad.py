#!/usr/bin/env python
#########################################################################################
#
# This script preps .nii data in uses Vladimir Frolov's straightening method in order
# to straighten the spinal cord
#
# ---------------------------------------------------------------------------------------
# Copyright (c) 2014 Polytechnique Montreal <www.neuro.polymtl.ca>
# Authors: Olivier Comtois
# Modified: 2015-07-8
#
# About the license: see the file LICENSE.TXT
#########################################################################################

import sct_utils as sct
from msct_parser import Parser
import os
import commands
import sys

class VladStraighten(object):
    def __init__(self, input_image, output_filnename="straight.nii.gz", verbose=1):
        self.input_image = input_image
        self.output_filename = output_filnename
        self.verbose = verbose

    def execute(self):
        # change input filename to mnc format
        fname_in = self.input_image
        fname_bare = str(fname_in).split(".", 1)[0]
        in_orient = fname_bare + "_RPI.nii.gz"

        manual_seg = "errsm_21_t2_manual_segmentation.nii.gz"

        fname_seg = str(fname_bare)+"_seg.nii.gz"
        fname_seg_orient = fname_seg + "_RPI.nii.gz"
        niigz_out = self.output_filename

        cmd = "sct_propseg -i "+self.input_image+" -t t2 -o ."
        sct.run(cmd)

        cmd = "sct_orientation -i "+self.input_image+" -s RPI -o "+in_orient
        sct.run(cmd)

        cmd = "sct_orientation -i "+fname_seg+" -s RPI -o "+fname_seg_orient
        sct.run(cmd)

        if os.path.isfile(niigz_out):
            os.remove(niigz_out)
        sct.printv(os.getcwd())
        cmd = "itk_spine_straighten "+in_orient+" "+fname_seg_orient+" "+niigz_out+" --seg"
        sct.printv(cmd)
        output = commands.getoutput(cmd)

        if not bool(output):
            os.remove(fname_seg)
            raise Exception(str(output))

        os.remove(fname_seg)
        sct.printv(output)

if __name__ == "__main__":

    # Initialize parser
    parser = Parser(__file__)

    parser.usage.set_description("This script preps .nii data in order to use Vladimir Frolov's straightening method in order to straighten the spinal cord")
    parser.add_option(name="-i",
                      type_value="image_nifti",
                      description="input image.",
                      mandatory=True,
                      example="t2.nii.gz")
    parser.add_option(name="-o",
                      type_value="file_output",
                      description="Output's filnename.",
                      mandatory=False,
                      example="result.nii.gz")

    arguments = parser.parse(sys.argv[1:])

    input_filename = arguments["-i"]

    sc = VladStraighten(input_filename)

    if "-o" in arguments:
        sc.output_filename = arguments["-o"]

    try:
        sc.execute()
    except Exception, e:
        sct.printv(e.message, type="error")

