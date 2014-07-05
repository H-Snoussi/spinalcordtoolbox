#!/usr/bin/env python
#########################################################################################
#
# Motion correction of dMRI data.
#
# Inspired by Xu et al. Neuroimage 2013.
#
# Details of the algorithm:
# - grouping of DW data only (every n volumes, default n=5)
# - average all b0
# - average DWI data within each group
# - average DWI of all groups
# - moco on DWI groups
# - moco on b=0, using target volume: last b=0
# - moco on all DMRI data
#
# ---------------------------------------------------------------------------------------
# Copyright (c) 2013 Polytechnique Montreal <www.neuro.polymtl.ca>
# Authors: Karun Raju, Tanguy Duval, Julien Cohen-Adad
# Modified: 2014-07-02
#
# About the license: see the file LICENSE.TXT
#########################################################################################

# TODO: line 371: param.fname_data = 'b0_mean.nii'. That does not make sense, since b0_mean is 3d, not 4d.
# TODO: use 3D spline approximation instead of LP filter.
# TODO: find clever approach for b=0 moco (if target is corrupted, then reg will fail)
# TODO: provide b0_mean and dwi_mean after moco
# TODO: verbose 1: txt, verbose 2: printed fig in png
# TDOD: we need two plots. Plot 1: X params with fitted spline, plot 2: Y param with fitted splines. Each plot will have all Z slices (with legend Z=0, Z=1, ...) and labels: y; translation (mm), xlabel: volume #. Plus add grid.

import sys
import os
import commands
import getopt
import time
import glob
import math
from sct_eddy_correct import sct_eddy_correct
from isct_moco import sct_moco
from isct_moco_spline import sct_moco_spline
from isct_moco_combine_matrix import sct_moco_combine_matrix

try:
    import nibabel
except ImportError:
    print '--- nibabel not installed! Exit program. ---'
    sys.exit(2)
try:
    import numpy as np
except ImportError:
    print '--- numpy not installed! Exit program. ---'
    sys.exit(2)

output_path = ''

# get path of the toolbox
status, path_sct = commands.getstatusoutput('echo $SCT_DIR')
# append path that contains scripts, to be able to load modules
sys.path.append(path_sct + '/scripts')
import sct_utils as sct

class param_class:
    def __init__(self):
    
        #============================================
        #Different Parameters
        #============================================
        self.debug                     = 0
        self.fname_data                = ''
        self.fname_bvecs               = ''
        self.fname_bvals               = ''
        self.fname_target              = ''
        self.fname_centerline          = ''
        self.output_path               = ''
        self.mat_final                 = ''
        self.mat_moco                  = ''
        self.todo                      = ''              
        self.dwi_group_size            = 5               # number of images averaged for 'dwi' method.
        self.suffix                    = '_moco'
        self.mask_size                 = 0               # sigma of gaussian mask in mm --> std of the kernel. Default is 0
        self.program                   = 'FLIRT'
        self.cost_function_flirt       = ''              # 'mutualinfo' | 'woods' | 'corratio' | 'normcorr' | 'normmi' | 'leastsquares'. Default is 'normcorr'.
        self.interp                    = 'trilinear'     #  Default is 'trilinear'. Additional options: trilinear,nearestneighbour,sinc,spline.
        self.spline_fitting            = 1
        self.delete_tmp_files          = 1
        self.merge_back                = 1
        self.verbose                   = 0

        #============================================
        #Eddy Current Distortion Parameters
        #============================================
        self.run_eddy                  = 0
        self.mat_eddy                  = ''
        self.min_norm                  = 0.001
        self.swapXY                    = 0

#=======================================================================================================================
# main
#=======================================================================================================================

def main():

    print '\n\n\n\n==================================================='
    print '          Running: sct_dmri_moco'
    print '===================================================\n\n\n\n'

    # initialization
    start_time = time.time()
    param = param_class()

    # Parameters for debug mode
    if param.debug:
        param.fname_data = path_sct+'/testing/data/errsm_23/dmri/dmri.nii.gz'
        param.fname_bvecs = path_sct+'/testing/data/errsm_23/dmri/bvecs.txt'

    # Check input parameters
    try:
        opts, args = getopt.getopt(sys.argv[1:],'hi:a:b:c:d:e:f:l:o:p:r:s:v:')
    except getopt.GetoptError:
        usage()
    for opt, arg in opts:
        if opt == '-h':
            usage()
        elif opt in ('-i'):
            param.fname_data = arg
        elif opt in ('-a'):
            param.fname_bvals = arg
        elif opt in ('-b'):
            param.fname_bvecs = arg
        elif opt in ('-c'):
            param.cost_function_flirt = arg
        elif opt in ('-d'):
            param.dwi_group_size = int(arg)
        elif opt in ('-e'):
            param.run_eddy = int(arg)
        elif opt in ('-f'):
            param.spline_fitting = int(arg)
        elif opt in ('-l'):
            param.fname_centerline = arg
        elif opt in ('-o'):
            param.output_path = arg
        elif opt in ('-p'):
            param.interp = arg
        elif opt in ('-r'):
            param.delete_tmp_files = int(arg)
        elif opt in ('-s'):
            param.mask_size = float(arg)
        elif opt in ('-v'):
            param.verbose = int(arg)

    # display usage if a mandatory argument is not provided
    if param.fname_data == '':
        print '\n\n\033[91mAll mandatory arguments are not provided\033[0m \n'
        usage()
    elif param.fname_bvecs == '' and param.fname_bvals == '':
        print '\n\n\033[91mAll mandatory arguments are not provided\033[0m \n'
        usage()

    if param.cost_function_flirt=='':  param.cost_function_flirt = 'normcorr'
    if param.output_path=='': param.output_path = os.getcwd() + '/'
    global output_path
    output_path = param.output_path

    print 'Input File:',param.fname_data
    print 'Bvecs File:',param.fname_bvecs
    if param.fname_bvals!='':
        print 'Bvals File:', param.fname_bvals

    # check existence of input files
    sct.check_file_exist(param.fname_data)
    sct.check_file_exist(param.fname_bvecs)

    # Get full path
    param.fname_data = os.path.abspath(param.fname_data)
    param.fname_bvecs = os.path.abspath(param.fname_bvecs)
    if param.fname_bvals!='':
        param.fname_bvals = os.path.abspath(param.fname_bvals)

    # Extract path, file and extension
    path_data, file_data, ext_data = sct.extract_fname(param.fname_data)

    # create temporary folder
    path_tmp = 'tmp.'+time.strftime("%y%m%d%H%M%S")
    sct.run('mkdir '+ path_tmp)

    # go to tmp folder
    os.chdir(path_tmp)

    fname_data_initial = param.fname_data

    # EDDY CORRECTION -- for debugging, it is possible to run code by commenting the next lines
    if param.run_eddy:
        param.output_path = ''
        sct_eddy_correct(param)
        param.fname_data = file_data+'_eddy.nii'

    # here, the variable "fname_data_initial" is also input, because it will be processed in the final step, where as
    # the param.fname_data will be the output of sct_eddy_correct.
    sct_dmri_moco(param,fname_data_initial)

    # come back to parent folder
    os.chdir('..')

    # Delete temporary files
    if param.delete_tmp_files == 1:
        print '\nDelete temporary files...'
        sct.run('rm -rf '+ path_tmp)

    # display elapsed time
    elapsed_time = time.time() - start_time
    print '\nFinished! Elapsed time: '+str(int(round(elapsed_time)))+'s'

    #To view results
    print '\nTo view results, type:'
    print 'fslview ' + param.output_path + file_data + param.suffix

#=======================================================================================================================
# Function sct_dmri_moco - Preparing Data For MOCO
#=======================================================================================================================

def sct_dmri_moco(param,fname_data_initial):
    
    fsloutput = 'export FSLOUTPUTTYPE=NIFTI; ' # for faster processing, all outputs are in NIFTI
    
    fname_data     = param.fname_data
    fname_bvecs    = param.fname_bvecs
    fname_bvals    = param.fname_bvals
    dwi_group_size = param.dwi_group_size

    # Extract path, file and extension
    path_data, file_data, ext_data = sct.extract_fname(fname_data)
    
    file_b0        = 'b0'
    file_dwi       = 'dwi'
    
    # Get size of data
    print '\nGet dimensions data...'
    nx, ny, nz, nt, px, py, pz, pt = sct.get_dimension(fname_data)
    print '.. '+str(nx)+' x '+str(ny)+' x '+str(nz)+' x '+str(nt)

    if fname_bvals=='':
        # Open bvecs file
        print '\nOpen bvecs file...'
        bvecs = []
        with open(fname_bvecs) as f:
            for line in f:
                bvecs_new = map(float, line.split())
                bvecs.append(bvecs_new)
    
        # Check if bvecs file is nx3
        if not len(bvecs[0][:]) == 3:
            print '.. WARNING: bvecs file is 3xn instead of nx3. Consider using sct_dmri_transpose_bvecs.'
            print 'Transpose bvecs...'
            # transpose bvecs
            bvecs = zip(*bvecs)

        # Identify b=0 and DWI images
        print '\nIdentify b=0 and DWI images...'
        index_b0 = []
        index_dwi = []
        for it in xrange(0,nt):
            if math.sqrt(math.fsum([i**2 for i in bvecs[it]])) < 0.01:
                index_b0.append(it)
            else:
                index_dwi.append(it)
        n_b0 = len(index_b0)
        n_dwi = len(index_dwi)
        print '.. Index of b=0:'+str(index_b0)
        print '.. Index of DWI:'+str(index_dwi)
        
    if fname_bvals!='':
        # Open bvals file
        print '\nOpen bvals file...'
        bvals = []
        with open(fname_bvals) as f:
            for line in f:
                bvals_new = map(float, line.split())
                bvals.append(bvecs_new)

        # Identify b=0 and DWI images
        print '\nIdentify b=0 and DWI images...'
        index_b0 = np.where(bvals>429 and bvals<4000)
        index_dwi = np.where(bvals<=429 or bvals>=4000)
        n_b0 = len(index_b0)
        n_dwi = len(index_dwi)
        print '.. Index of b=0:'+str(index_b0)
        print '.. Index of DWI:'+str(index_dwi)

    # Split into T dimension
    print '\nSplit along T dimension...'
    status, output = sct.run(fsloutput+'fslsplit '+fname_data + ' ' + 'tmp.data_splitT')

    # Merge b=0 images
    print '\nMerge b=0...'
    fname_b0_merge = file_b0
    cmd = fsloutput + 'fslmerge -t ' + fname_b0_merge
    for iT in range(n_b0):
        cmd = cmd + ' ' + 'tmp.data_splitT' + str(index_b0[iT]).zfill(4) 
    status, output = sct.run(cmd)
    print '.. File created: ',fname_b0_merge

    # Average b=0 images
    print '\nAverage b=0...'
    fname_b0_mean = 'b0_mean' 
    cmd = fsloutput + 'fslmaths ' + fname_b0_merge + ' -Tmean ' + fname_b0_mean
    status, output = sct.run(cmd)

    # Number of DWI groups
    nb_groups = int(math.floor(n_dwi/dwi_group_size))
    
    # Generate groups indexes
    group_indexes = []
    for iGroup in range(nb_groups):
        group_indexes.append(index_dwi[(iGroup*dwi_group_size):((iGroup+1)*dwi_group_size)])
    
    # add the remaining images to the last DWI group
    nb_remaining = n_dwi%dwi_group_size # number of remaining images
    if nb_remaining>0:
        nb_groups += 1
        group_indexes.append(index_dwi[len(index_dwi)-nb_remaining:len(index_dwi)])

    # Size of DWI groups                        
    for iGroup in range(nb_groups):
        print  '\nGroup ',str((iGroup+1)),' of DW images'
    
        index_dwi_i = group_indexes[iGroup]
        nb_dwi_i = len(index_dwi_i)
        
        # Merge DW Images
        print '\nMerge DW images...'        
        fname_dwi_merge_i = file_dwi + '_' + str(iGroup)
        cmd = fsloutput + 'fslmerge -t ' + fname_dwi_merge_i
        for iT in range(nb_dwi_i):
            cmd = cmd +' ' + 'tmp.data_splitT' + str(index_dwi_i[iT]).zfill(4) 
        status, output = sct.run(cmd)

        # Average DW Images
        print '\nAverage DW images...'
        fname_dwi_mean = file_dwi + '_mean' + '_' + str(iGroup)
        cmd = fsloutput + 'fslmaths ' + fname_dwi_merge_i + ' -Tmean ' + fname_dwi_mean
        status, output = sct.run(cmd)

    # Merge DWI groups means
    print '\nMerging DW files...'
    fname_dwi_groups_means_merge = 'dwi_averaged_groups' 
    cmd = fsloutput + 'fslmerge -t ' + fname_dwi_groups_means_merge
    for iGroup in range(nb_groups):
        cmd = cmd + ' ' + file_dwi + '_mean_' + str(iGroup)
    status, output = sct.run(cmd)

    # Average DW Images
    print '\nAveraging all DW images...'
    fname_dwi_mean = 'dwi_mean'  
    cmd = fsloutput + 'fslmaths ' + fname_dwi_groups_means_merge + ' -Tmean ' + fname_dwi_mean
    status, output = sct.run(cmd)

    # Estimate moco on dwi groups
    print '\n\n------------------------------------------------------------------------------'
    print 'Estimating motion based on DW groups...'
    print '------------------------------------------------------------------------------\n'
    param.fname_data = 'dwi_averaged_groups.nii'
#    param.fname_target =  path_data + 'dwi_mean.nii'
    param.fname_target =  file_dwi + '_mean_' + str(0)
    param.output_path = ''
    param.todo = 'estimate_and_apply'
    param.mat_moco = 'dwigroups_param.mat'
    sct_moco(param)

    # Estimate moco on b0 groups
    param.fname_data = 'b0_mean.nii'
    if index_dwi[0]!=0:
        # If first DWI is not the first volume, then there is a least one b=0 image before. In that case
        # select it as the target image for registration of all b=0
        param.fname_target = 'tmp.data_splitT' + str(index_b0[index_dwi[0]-1]).zfill(4) + '.nii'
    else:
        # If first DWI is the first volume, then the target b=0 is the first b=0 from the index_b0.
        param.fname_target = 'tmp.data_splitT' + str(index_b0[0]).zfill(4) + '.nii'
    param.output_path = ''
    param.todo = 'estimate_and_apply'
    param.mat_moco = 'b0groups_param.mat'
    sct_moco(param)

    #Copy registration matrix for every dwi based on dwi_averaged_groups
    print '\n\n------------------------------------------------------------------------------'
    print 'Copy registration matrix for every dwi based on dwi_averaged_groups matrix...'
    print '------------------------------------------------------------------------------\n'
    mat_final = 'mat_final/'
    if not os.path.exists(mat_final): os.makedirs(mat_final)

    for iGroup in range(nb_groups):
        for dwi in range(len(group_indexes[iGroup])):
            for i_Z in range(nz):
                cmd = 'cp '+'dwigroups_param.mat/'+'mat.T'+str(iGroup)+'_Z'+str(i_Z)+'.txt'+' '+mat_final+'mat.T'+str(group_indexes[iGroup][dwi])+'_Z'+str(i_Z)+'.txt'
                status, output = sct.run(cmd)

    index = np.argmin(np.abs(np.array(index_dwi) - index_b0[len(index_b0)-1]))
    for b0 in range(len(index_b0)):
        for i_Z in range(nz):
            cmd = 'cp '+mat_final+'mat.T'+ str(index_dwi[index]) +'_Z'+str(i_Z)+'.txt'+' '+mat_final+'mat.T'+str(index_b0[b0])+'_Z'+str(i_Z)+'.txt'
            status, output = sct.run(cmd)

    #Renaming Files
    nz1 = len(glob.glob('b0groups_param.mat/mat.T0_Z*.txt'))
    nt1 = len(glob.glob('b0groups_param.mat/mat.T*_Z0.txt'))
    for iT in range(nt1):
        if iT!=index_b0[iT]:
            for iZ in range(nz1):
                cmd = 'mv ' + 'b0groups_param.mat/mat.T'+str(iT)+'_Z'+str(iZ)+'.txt' + ' ' + 'b0groups_param.mat/mat.T'+str(index_b0[iT])+'_Z'+str(iZ)+'.txt'
                status, output = sct.run(cmd)

    #combining Motion Matrices
    sct_moco_combine_matrix('b0groups_param.mat',mat_final)

    if param.spline_fitting:
        #Spline Regularization along T
        sct_moco_spline(mat_final,nt,nz,param.verbose)

    if param.run_eddy:
        #combining eddy Matrices
        sct_moco_combine_matrix('mat_eddy',mat_final)

    #Apply moco on all dmri data
    print '\n\n\n------------------------------------------------------------------------------'
    print 'Apply moco on all dmri data...'
    print '------------------------------------------------------------------------------\n'
    param.fname_data =  fname_data_initial
    param.fname_target = fname_data_initial
    param.output_path = output_path
    param.mat_final = mat_final
    param.todo = 'apply'
    sct_moco(param)
#=======================================================================================================================
# usage
#=======================================================================================================================
def usage():
    print '\n' \
        ''+os.path.basename(__file__)+'\n' \
        '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n' \
        'Part of the Spinal Cord Toolbox <https://sourceforge.net/projects/spinalcordtoolbox>\n' \
        '\n'\
        'DESCRIPTION\n' \
        '  Motion correction of DWI data. Uses slice-by-slice and group-wise registration.\n' \
        '\n' \
        'USAGE\n' \
        '  '+os.path.basename(__file__)+' -i <dmri> -b <bvecs>\n' \
        '\n' \
        'MANDATORY ARGUMENTS\n' \
        '  -i <dmri>    diffusion data\n' \
        '  -b <bvecs>   bvecs file\n' \
        '\n' \
        'OPTIONAL ARGUMENTS\n' \
        '  -o           Specify Output path.\n' \
        '  -a <bvals>   bvals file. Used to detect low-bvals images : more robust \n' \
        '  -d           DWI Group Size. Successive images are merged to increase robustness. Default=5\n' \
        '  -e           Eddy Correction using opposite gradient directions. Default=0 \n' \
        '               N.B. Only use this option if pairs of opposite gradient images were adjacent in time\n' \
        '  -s           Gaussian mask_size - Specify mask_size in millimeters. Default value of mask_size is 0. We recommend s=15. \n' \
        '  -l           Centerline file can be given to specify the centre of Gaussian Mask (by default, gaussian mask is centered). Need -s. \n' \
        '  -c           Cost function FLIRT - mutualinfo | woods | corratio | normcorr | normmi | leastsquares. Default is <normcorr>..\n' \
        '  -p           Interpolation - Default is trilinear. Additional options: nearestneighbour,sinc,spline.\n' \
        '  -f           set value to 0 if spline regularization along T is not required. Default value is 1. \n' \
        '  -v           Set verbose=1 for plotting graphs. Default value is 0 \n' \
        '  -r           Set value to 0 for not deleting temp files. Default value is 1 \n' \
        '  -h           help. Show this message.\n' \
        '\n'\
        'EXAMPLE:\n' \
        '  '+os.path.basename(__file__)+' -i dmri.nii -b bvecs_t.txt \n'
    
    #Exit Program
    sys.exit(2)

#=======================================================================================================================
# Start program
#=======================================================================================================================
if __name__ == "__main__":
    # call main function
    main()