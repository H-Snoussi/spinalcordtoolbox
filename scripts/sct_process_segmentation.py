#!/usr/bin/env python
#########################################################################################
#
# Perform various types of processing from the spinal cord segmentation (e.g. extract centerline, compute CSA, etc.).
# (extract_centerline) extract the spinal cord centerline from the segmentation. Output file is an image in the same
# space as the segmentation.
#
#
# ---------------------------------------------------------------------------------------
# Copyright (c) 2014 Polytechnique Montreal <www.neuro.polymtl.ca>
# Author: Benjamin De Leener, Julien Touati, Gabriel Mangeat
# Modified: 2014-07-20 by jcohenadad
#
# About the license: see the file LICENSE.TXT
#########################################################################################
# TODO: the import of scipy.misc imsave was moved to the specific cases (orth and ellipse) in order to avoid issue #62. This has to be cleaned in the future.

import sys
import getopt
import os
import commands
from random import randint
import time
import numpy as np
import scipy
import nibabel
import sct_utils as sct
from msct_nurbs import NURBS
from sct_image import get_orientation_3d, set_orientation
from sct_straighten_spinalcord import smooth_centerline
from msct_image import Image
from shutil import move, copyfile
from msct_parser import Parser


# DEFAULT PARAMETERS
class Param:
    ## The constructor
    def __init__(self):
        self.debug = 0
        self.verbose = 1  # verbose
        self.step = 1  # step of discretized plane in mm default is min(x_scale,py)
        self.remove_temp_files = 1
        self.smoothing_param = 0  # window size (in mm) for smoothing CSA along z. 0 for no smoothing.
        self.figure_fit = 0
        self.slices = ''
        self.vertebral_levels = ''
        self.type_window = 'hanning'  # for smooth_centerline @sct_straighten_spinalcord
        self.window_length = 50  # for smooth_centerline @sct_straighten_spinalcord
        self.algo_fitting = 'hanning'  # nurbs, hanning

def get_parser():
    """
    :return: Returns the parser with the command line documentation contained in it.
    """
    # Initialize the parser
    parser = Parser(__file__)
    parser.usage.set_description("""This program is used to get the centerline of the spinal cord of a subject by using one of the three methods describe in the -method flag .""")
    parser.add_option(name='-i',
                      type_value='image_nifti',
                      description='Spinal Cord segmentation',
                      mandatory=True,
                      example='seg.nii.gz')
    parser.add_option(name='-p',
                      type_value='multiple_choice',
                      description='type of process to be performed:\n'
                                  '- centerline: extract centerline as binary file.\n'
                                  '- label-vert: Transform segmentation into vertebral level using a file that contains labels with disc value (flag: -discfile)\n'
                                  '- length: compute length of the segmentation.\n'
                                  '- csa: computes cross-sectional area by counting pixels in each'
                                  '  slice and then geometrically adjusting using centerline orientation. Outputs:\n'
                                  '  - angle_image.nii.gz: the cord segmentation (nifti file) where each slice\'s value is equal to the CSA (mm^2),\n'
                                  '  - csa_image.nii.gz: the cord segmentation (nifti file) where each slice\'s value is equal to the angle (in degrees) between the spinal cord centerline and the inferior-superior direction,\n'
                                  '  - csa_per_slice.txt: a CSV text file with z (1st column) and CSA in mm^2 (2nd column),\n'
                                  '  - and if you select the options -z or -vert, csa_mean and csa_volume: mean CSA and volume across the selected slices or vertebral levels is ouptut in CSV text files, an MS Excel files and a pickle files.\n',
                      mandatory=True,
                      example=['centerline', 'label-vert', 'length', 'csa'])
    parser.usage.addSection('Optional Arguments')
    parser.add_option(name="-ofolder",
                      type_value="folder_creation",
                      description="In case you choose the option \"-p csa\", this option allows you to specify the output folder for the result files. If this folder does not exist, it will be created, otherwise the result files will be output in the pre-existing folder.",
                      mandatory=False,
                      example="My_Output_Folder/",
                      default_value="")
    parser.add_option(name='-overwrite',
                      type_value='int',
                      description="""In the case you specified, in flag \"-ofolder\", a pre-existing folder that already includes a .xls result file (see flags \"-p csa\" and \"-z\" or \"-vert\"), this option will allow you to overwrite the .xls file (\"-overwrite 1\") or to add the results to it (\"-overwrite 0\").""",
                      mandatory=False,
                      default_value=0)
    parser.add_option(name='-s',
                      type_value=None,
                      description='Window size (in mm) for smoothing CSA. 0 for no smoothing.',
                      mandatory=False,
                      deprecated_by='-size')
    parser.add_option(name='-z',
                      type_value='str',
                      description= 'Slice range to compute the CSA across (requires \"-p csa\").',
                      mandatory=False,
                      example='5:23')
    parser.add_option(name='-l',
                      type_value='str',
                      description= 'Vertebral levels to compute the CSA across (requires \"-p csa\"). Example: 2:9 for C2 to T2.',
                      mandatory=False,
                      deprecated_by='-vert',
                      example='2:9')
    parser.add_option(name='-vert',
                      type_value='str',
                      description= 'Vertebral levels to compute the CSA across (requires \"-p csa\"). Example: 2:9 for C2 to T2.',
                      mandatory=False,
                      example='2:9')
    parser.add_option(name='-t',
                      type_value='image_nifti',
                      description='Vertebral labeling file. Only use with flag -vert',
                      mandatory=False,
                      deprecated_by='-vertfile',
                      default_value='label/template/PAM50_levels.nii.gz')
    parser.add_option(name='-vertfile',
                      type_value='image_nifti',
                      description='Vertebral labeling file. Only use with flag -vert',
                      mandatory=False,
                      default_value='./label/template/PAM50_levels.nii.gz')
    parser.add_option(name='-discfile',
                      type_value='image_nifti',
                      description='Disc labeling. Only use with -p label-vert',
                      mandatory=False)
    parser.add_option(name='-r',
                      type_value='multiple_choice',
                      description= 'Removes the temporary folder and debug folder used for the algorithm at the end of execution',
                      mandatory=False,
                      default_value='1',
                      example=['0', '1'])
    parser.add_option(name='-size',
                      type_value='int',
                      description='Window size (in mm) for smoothing CSA. 0 for no smoothing.',
                      mandatory=False,
                      default_value=0)
    parser.add_option(name='-a',
                      type_value='multiple_choice',
                      description= 'Algorithm for curve fitting.',
                      mandatory=False,
                      default_value='nurbs',
                      example=['hanning', 'nurbs'])
    parser.add_option(name='-no-angle',
                      type_value='multiple_choice',
                      description='0: angle correction for csa computation. 1: no angle correction.',
                      mandatory=False,
                      example=['0', '1'],
                      default_value='0')
    parser.add_option(name='-v',
                      type_value='multiple_choice',
                      description='1: display on, 0: display off (default)',
                      mandatory=False,
                      example=['0', '1', '2'],
                      default_value='1')
    parser.add_option(name='-h',
                      type_value=None,
                      description='display this help',
                      mandatory=False)

    return parser



# MAIN
# ==========================================================================================
def main(args):

    parser = get_parser()
    arguments = parser.parse(args)

    # Initialization
    path_script = os.path.dirname(__file__)
    fsloutput = 'export FSLOUTPUTTYPE=NIFTI; ' # for faster processing, all outputs are in NIFTI
    processes = ['centerline', 'csa', 'length']
    verbose = param.verbose
    start_time = time.time()
    remove_temp_files = param.remove_temp_files
    # spline_smoothing = param.spline_smoothing
    step = param.step
    smoothing_param = param.smoothing_param
    figure_fit = param.figure_fit
    slices = param.slices
    vert_lev = param.vertebral_levels
    angle_correction = True

    fname_segmentation = arguments['-i']
    name_process = arguments['-p']
    overwrite = 0
    if "-ofolder" in arguments:
        output_folder = sct.slash_at_the_end(arguments["-ofolder"], slash=1)
    else:
        seg_path, seg_file, seg_ext = sct.extract_fname(os.path.abspath(fname_segmentation))
        output_folder = seg_path
    if '-overwrite' in arguments:
        overwrite = arguments['-overwrite']
    if '-vert' in arguments:
        vert_lev = arguments['-vert']
    if '-r' in arguments:
        remove_temp_files = arguments['-r']
    if '-size' in arguments:
        smoothing_param = arguments['-size']
    if '-vertfile' in arguments:
        fname_vertebral_labeling = arguments['-vertfile']
    if '-v' in arguments:
        verbose = arguments['-v']
    if '-z' in arguments:
        slices = arguments['-z']
    if '-a' in arguments:
        param.algo_fitting = arguments['-a']
    if '-no-angle' in arguments:
        if arguments['-no-angle'] == '1':
            angle_correction = False
        elif arguments['-no-angle'] == '0':
            angle_correction = True

    # update fields
    param.verbose = verbose

    # print arguments
    print '\nCheck parameters:'
    print '.. segmentation file:             '+fname_segmentation

    if name_process == 'centerline':
        fname_output = extract_centerline(fname_segmentation, remove_temp_files, verbose=param.verbose, algo_fitting=param.algo_fitting)
        # to view results
        sct.printv('\nDone! To view results, type:', param.verbose)
        sct.printv('fslview '+fname_segmentation+' '+fname_output+' -l Red &\n', param.verbose, 'info')

    if name_process == 'csa':
        compute_csa(fname_segmentation, output_folder, overwrite, verbose, remove_temp_files, step, smoothing_param, figure_fit, slices, vert_lev, fname_vertebral_labeling, algo_fitting = param.algo_fitting, type_window= param.type_window, window_length=param.window_length, angle_correction=angle_correction)

    if name_process == 'label-vert':
        if '-discfile' in arguments:
            fname_disc_label = arguments['-discfile']
        else:
            sct.printv('\nERROR: Disc label file is mandatory (flag: -discfile).\n', 1, 'error')
        label_vert(fname_segmentation, fname_disc_label)

    if name_process == 'length':
        result_length = compute_length(fname_segmentation, remove_temp_files, verbose=verbose)
        sct.printv('\nLength of the segmentation = '+str(round(result_length,2))+' mm\n', verbose, 'info')

    # End of Main



# compute the length of the spinal cord
# ==========================================================================================
def compute_length(fname_segmentation, remove_temp_files, verbose = 0):
    from math import sqrt

    # Extract path, file and extension
    fname_segmentation = os.path.abspath(fname_segmentation)
    path_data, file_data, ext_data = sct.extract_fname(fname_segmentation)

    # create temporary folder
    sct.printv('\nCreate temporary folder...', verbose)
    path_tmp = sct.slash_at_the_end('tmp.'+time.strftime("%y%m%d%H%M%S") + '_'+str(randint(1, 1000000)), 1)
    sct.run('mkdir '+path_tmp, verbose)

    # copy files into tmp folder
    sct.run('cp '+fname_segmentation+' '+path_tmp)

    # go to tmp folder
    os.chdir(path_tmp)

    # Change orientation of the input centerline into RPI
    sct.printv('\nOrient centerline to RPI orientation...', param.verbose)
    im_seg = Image(file_data+ext_data)
    fname_segmentation_orient = 'segmentation_rpi' + ext_data
    im_seg_orient = set_orientation(im_seg, 'RPI')
    im_seg_orient.setFileName(fname_segmentation_orient)
    im_seg_orient.save()

    # Get dimension
    sct.printv('\nGet dimensions...', param.verbose)
    nx, ny, nz, nt, px, py, pz, pt = im_seg_orient.dim
    sct.printv('.. matrix size: '+str(nx)+' x '+str(ny)+' x '+str(nz), param.verbose)
    sct.printv('.. voxel size:  '+str(px)+'mm x '+str(py)+'mm x '+str(pz)+'mm', param.verbose)

    # smooth segmentation/centerline
    #x_centerline_fit, y_centerline_fit, z_centerline, x_centerline_deriv,y_centerline_deriv,z_centerline_deriv = smooth_centerline(fname_segmentation_orient, param, 'hanning', 1)
    x_centerline_fit, y_centerline_fit, z_centerline, x_centerline_deriv,y_centerline_deriv,z_centerline_deriv = smooth_centerline(fname_segmentation_orient, type_window='hanning', window_length=80, algo_fitting='hanning', verbose = verbose)
    # compute length of centerline
    result_length = 0.0
    for i in range(len(x_centerline_fit)-1):
        result_length += sqrt(((x_centerline_fit[i+1]-x_centerline_fit[i])*px)**2+((y_centerline_fit[i+1]-y_centerline_fit[i])*py)**2+((z_centerline[i+1]-z_centerline[i])*pz)**2)

    return result_length



# extract_centerline
# ==========================================================================================
def extract_centerline(fname_segmentation, remove_temp_files, verbose = 0, algo_fitting = 'hanning', type_window = 'hanning', window_length = 80):

    # Extract path, file and extension
    fname_segmentation = os.path.abspath(fname_segmentation)
    path_data, file_data, ext_data = sct.extract_fname(fname_segmentation)

    # create temporary folder
    sct.printv('\nCreate temporary folder...', verbose)
    path_tmp = sct.slash_at_the_end('tmp.'+time.strftime("%y%m%d%H%M%S") + '_'+str(randint(1, 1000000)), 1)
    sct.run('mkdir '+path_tmp, verbose)

    # Copying input data to tmp folder
    sct.printv('\nCopying data to tmp folder...', verbose)
    sct.run('sct_convert -i '+fname_segmentation+' -o '+path_tmp+'segmentation.nii.gz', verbose)

    # go to tmp folder
    os.chdir(path_tmp)

    # Change orientation of the input centerline into RPI
    sct.printv('\nOrient centerline to RPI orientation...', verbose)
    # fname_segmentation_orient = 'segmentation_RPI.nii.gz'
    # BELOW DOES NOT WORK (JULIEN, 2015-10-17)
    # im_seg = Image(file_data+ext_data)
    # set_orientation(im_seg, 'RPI')
    # im_seg.setFileName(fname_segmentation_orient)
    # im_seg.save()
    sct.run('sct_image -i segmentation.nii.gz -setorient RPI -o segmentation_RPI.nii.gz', verbose)

    # Open segmentation volume
    sct.printv('\nOpen segmentation volume...', verbose)
    im_seg = Image('segmentation_RPI.nii.gz')
    data = im_seg.data

    # Get size of data
    sct.printv('\nGet data dimensions...', verbose)
    nx, ny, nz, nt, px, py, pz, pt = im_seg.dim
    sct.printv('.. matrix size: '+str(nx)+' x '+str(ny)+' x '+str(nz), verbose)
    sct.printv('.. voxel size:  '+str(px)+'mm x '+str(py)+'mm x '+str(pz)+'mm', verbose)

    # # Get dimension
    # sct.printv('\nGet dimensions...', verbose)
    # nx, ny, nz, nt, px, py, pz, pt = im_seg.dim
    #
    # # Extract orientation of the input segmentation
    # orientation = get_orientation(im_seg)
    # sct.printv('\nOrientation of segmentation image: ' + orientation, verbose)
    #
    # sct.printv('\nOpen segmentation volume...', verbose)
    # data = im_seg.data
    # hdr = im_seg.hdr

    # Extract min and max index in Z direction
    X, Y, Z = (data>0).nonzero()
    min_z_index, max_z_index = min(Z), max(Z)
    x_centerline = [0 for i in range(0,max_z_index-min_z_index+1)]
    y_centerline = [0 for i in range(0,max_z_index-min_z_index+1)]
    z_centerline = [iz for iz in range(min_z_index, max_z_index+1)]
    # Extract segmentation points and average per slice
    for iz in range(min_z_index, max_z_index+1):
        x_seg, y_seg = (data[:,:,iz]>0).nonzero()
        x_centerline[iz-min_z_index] = np.mean(x_seg)
        y_centerline[iz-min_z_index] = np.mean(y_seg)
    for k in range(len(X)):
        data[X[k], Y[k], Z[k]] = 0

    # extract centerline and smooth it
    x_centerline_fit, y_centerline_fit, z_centerline_fit, x_centerline_deriv, y_centerline_deriv, z_centerline_deriv = smooth_centerline('segmentation_RPI.nii.gz', type_window = type_window, window_length = window_length, algo_fitting = algo_fitting, verbose = verbose)

    if verbose == 2:
            import matplotlib.pyplot as plt

            #Creation of a vector x that takes into account the distance between the labels
            nz_nonz = len(z_centerline)
            x_display = [0 for i in range(x_centerline_fit.shape[0])]
            y_display = [0 for i in range(y_centerline_fit.shape[0])]
            for i in range(0, nz_nonz, 1):
                x_display[int(z_centerline[i]-z_centerline[0])] = x_centerline[i]
                y_display[int(z_centerline[i]-z_centerline[0])] = y_centerline[i]

            plt.figure(1)
            plt.subplot(2,1,1)
            plt.plot(z_centerline_fit, x_display, 'ro')
            plt.plot(z_centerline_fit, x_centerline_fit)
            plt.xlabel("Z")
            plt.ylabel("X")
            plt.title("x and x_fit coordinates")

            plt.subplot(2,1,2)
            plt.plot(z_centerline_fit, y_display, 'ro')
            plt.plot(z_centerline_fit, y_centerline_fit)
            plt.xlabel("Z")
            plt.ylabel("Y")
            plt.title("y and y_fit coordinates")
            plt.show()

    # Create an image with the centerline
    min_z_index, max_z_index = int(round(min(z_centerline_fit))), int(round(max(z_centerline_fit)))
    for iz in range(min_z_index, max_z_index+1):
        data[round(x_centerline_fit[iz-min_z_index]), round(y_centerline_fit[iz-min_z_index]), iz] = 1 # if index is out of bounds here for hanning: either the segmentation has holes or labels have been added to the file
    # Write the centerline image in RPI orientation
    # hdr.set_data_dtype('uint8') # set imagetype to uint8
    sct.printv('\nWrite NIFTI volumes...', verbose)
    im_seg.data = data
    im_seg.setFileName('centerline_RPI.nii.gz')
    im_seg.changeType('uint8')
    im_seg.save()

    sct.printv('\nSet to original orientation...', verbose)
    # get orientation of the input data
    im_seg_original = Image('segmentation.nii.gz')
    orientation = im_seg_original.orientation
    sct.run('sct_image -i centerline_RPI.nii.gz -setorient '+orientation+' -o centerline.nii.gz')

    # create a txt file with the centerline
    name_output_txt = 'centerline.txt'
    sct.printv('\nWrite text file...', verbose)
    file_results = open(name_output_txt, 'w')
    for i in range(min_z_index, max_z_index+1):
        file_results.write(str(int(i)) + ' ' + str(x_centerline_fit[i-min_z_index]) + ' ' + str(y_centerline_fit[i-min_z_index]) + '\n')
    file_results.close()

    # come back to parent folder
    os.chdir('..')

    # Generate output files
    sct.printv('\nGenerate output files...', verbose)
    sct.generate_output_file(path_tmp+'centerline.nii.gz', file_data+'_centerline.nii.gz')
    sct.generate_output_file(path_tmp+'centerline.txt', file_data+'_centerline.txt')

    # Remove temporary files
    if remove_temp_files:
        sct.printv('\nRemove temporary files...', verbose)
        sct.run('rm -rf '+path_tmp, verbose)

    return file_data+'_centerline.nii.gz'


# compute_csa
# ==========================================================================================
def compute_csa(fname_segmentation, output_folder, overwrite, verbose, remove_temp_files, step, smoothing_param, figure_fit, slices, vert_levels, fname_vertebral_labeling='', algo_fitting='hanning', type_window='hanning', window_length=80, angle_correction=True):

    from math import degrees

    # Extract path, file and extension
    fname_segmentation = os.path.abspath(fname_segmentation)
    # path_data, file_data, ext_data = sct.extract_fname(fname_segmentation)

    # create temporary folder
    sct.printv('\nCreate temporary folder...', verbose)
    path_tmp = sct.slash_at_the_end('tmp.'+time.strftime("%y%m%d%H%M%S") + '_'+str(randint(1, 1000000)), 1)
    sct.run('mkdir '+path_tmp, verbose)

    # Copying input data to tmp folder
    sct.printv('\nCopying input data to tmp folder and convert to nii...', verbose)
    sct.run('sct_convert -i '+fname_segmentation+' -o '+path_tmp+'segmentation.nii.gz', verbose)
    # go to tmp folder
    os.chdir(path_tmp)
    # Change orientation of the input segmentation into RPI
    sct.printv('\nChange orientation to RPI...', verbose)
    sct.run('sct_image -i segmentation.nii.gz -setorient RPI -o segmentation_RPI.nii.gz', verbose)

    # Open segmentation volume
    sct.printv('\nOpen segmentation volume...', verbose)
    im_seg = Image('segmentation_RPI.nii.gz')
    data_seg = im_seg.data
    # hdr_seg = im_seg.hdr

    # Get size of data
    sct.printv('\nGet data dimensions...', verbose)
    nx, ny, nz, nt, px, py, pz, pt = im_seg.dim
    sct.printv('  ' + str(nx) + ' x ' + str(ny) + ' x ' + str(nz), verbose)

    # # Extract min and max index in Z direction
    X, Y, Z = (data_seg > 0).nonzero()
    min_z_index, max_z_index = min(Z), max(Z)

    # extract centerline and smooth it
    x_centerline_fit, y_centerline_fit, z_centerline, x_centerline_deriv, y_centerline_deriv, z_centerline_deriv = smooth_centerline('segmentation_RPI.nii.gz', algo_fitting=algo_fitting, type_window=type_window, window_length=window_length, nurbs_pts_number=3000, phys_coordinates=True, verbose=verbose, all_slices=False)

    # transform centerline coordinates into voxel space for further use
    coord_voxel_centerline = im_seg.transfo_phys2pix([[x_centerline_fit[i], y_centerline_fit[i], z_centerline[i]] for i in range(len(z_centerline))])
    z_centerline_fit_vox = [coord[2] for coord in coord_voxel_centerline]

    # average over slices
    P_x = np.array(x_centerline_fit)
    P_y = np.array(y_centerline_fit)
    P_z = np.array(z_centerline)
    P_z_vox = np.array(z_centerline_fit_vox)
    P_x_d = np.array(x_centerline_deriv)
    P_y_d = np.array(y_centerline_deriv)
    P_z_d = np.array(z_centerline_deriv)

    P_z_vox = np.array([int(np.round(P_z_vox[i])) for i in range(0, len(P_z_vox))])
    # not perfect but works (if "enough" points), in order to deal with missing z slices
    for i in range(min(P_z_vox), max(P_z_vox) + 1, 1):
        if i not in P_z_vox:
            P_x_temp = np.insert(P_x, np.where(P_z_vox == i - 1)[-1][-1] + 1, (P_x[np.where(P_z_vox == i - 1)[-1][-1]] + P_x[np.where(P_z_vox == i - 1)[-1][-1] + 1]) / 2)
            P_y_temp = np.insert(P_y, np.where(P_z_vox == i - 1)[-1][-1] + 1, (P_y[np.where(P_z_vox == i - 1)[-1][-1]] + P_y[np.where(P_z_vox == i - 1)[-1][-1] + 1]) / 2)
            P_z_temp = np.insert(P_z, np.where(P_z_vox == i - 1)[-1][-1] + 1, (P_z[np.where(P_z_vox == i - 1)[-1][-1]] + P_z[np.where(P_z_vox == i - 1)[-1][-1] + 1]) / 2)
            P_x_d_temp = np.insert(P_x_d, np.where(P_z_vox == i - 1)[-1][-1] + 1, (P_x_d[np.where(P_z_vox == i - 1)[-1][-1]] + P_x_d[np.where(P_z_vox == i - 1)[-1][-1] + 1]) / 2)
            P_y_d_temp = np.insert(P_y_d, np.where(P_z_vox == i - 1)[-1][-1] + 1, (P_y_d[np.where(P_z_vox == i - 1)[-1][-1]] + P_y_d[np.where(P_z_vox == i - 1)[-1][-1] + 1]) / 2)
            P_z_d_temp = np.insert(P_z_d, np.where(P_z_vox == i - 1)[-1][-1] + 1, (P_z_d[np.where(P_z_vox == i - 1)[-1][-1]] + P_z_d[np.where(P_z_vox == i - 1)[-1][-1] + 1]) / 2)
            P_x, P_y, P_z, P_x_d, P_y_d, P_z_d = P_x_temp, P_y_temp, P_z_temp, P_x_d_temp, P_y_d_temp, P_z_d_temp

    coord_mean = np.array([[np.mean(P_x[P_z_vox == i]), np.mean(P_y[P_z_vox == i]), np.mean(P_z[P_z_vox == i])] for i in range(min(P_z_vox), max(P_z_vox) + 1, 1)])
    x_centerline_fit = coord_mean[:, :][:, 0]
    y_centerline_fit = coord_mean[:, :][:, 1]
    coord_mean_d = np.array([[np.mean(P_x_d[P_z_vox == i]), np.mean(P_y_d[P_z_vox == i]), np.mean(P_z_d[P_z_vox == i])] for i in range(min(P_z_vox), max(P_z_vox) + 1, 1)])
    z_centerline = coord_mean[:, :][:, 2]
    x_centerline_deriv = coord_mean_d[:, :][:, 0]
    y_centerline_deriv = coord_mean_d[:, :][:, 1]
    z_centerline_deriv = coord_mean_d[:, :][:, 2]

    # Compute CSA
    sct.printv('\nCompute CSA...', verbose)

    # Empty arrays in which CSA for each z slice will be stored
    csa = np.zeros(max_z_index-min_z_index+1)
    angles = np.zeros(max_z_index - min_z_index + 1)

    for iz in xrange(min_z_index, max_z_index+1):
        if angle_correction:
            # in the case of problematic segmentation (e.g., non continuous segmentation often at the extremities), display a warning but do not crash
            try:
                # compute the vector normal to the plane
                normal = normalize(np.array([x_centerline_deriv[iz-min_z_index], y_centerline_deriv[iz-min_z_index], z_centerline_deriv[iz-min_z_index]]))

            except IndexError:
                sct.printv('WARNING: Your segmentation does not seem continuous, which could cause wrong estimations at the problematic slices. Please check it, especially at the extremities.', type='warning')

            # compute the angle between the normal vector of the plane and the vector z
            angle = np.arccos(np.dot(normal, [0, 0, 1]))
        else:
            angle = 0.0

        # compute the number of voxels, assuming the segmentation is coded for partial volume effect between 0 and 1.
        number_voxels = np.sum(data_seg[:, :, iz])

        # compute CSA, by scaling with voxel size (in mm) and adjusting for oblique plane
        csa[iz-min_z_index] = number_voxels * px * py * np.cos(angle)
        angles[iz - min_z_index] = degrees(angle)

    sct.printv('\nSmooth CSA across slices...', verbose)
    if smoothing_param:
        from msct_smooth import smoothing_window
        sct.printv('.. Hanning window: '+str(smoothing_param)+' mm', verbose)
        csa_smooth = smoothing_window(csa, window_len=smoothing_param/pz, window='hanning', verbose=0)
        # display figure
        if verbose == 2:
            import matplotlib.pyplot as plt
            plt.figure()
            z_centerline_scaled = [x * pz for x in z_centerline]
            pltx, = plt.plot(z_centerline_scaled, csa, 'bo')
            pltx_fit, = plt.plot(z_centerline_scaled, csa_smooth, 'r', linewidth=2)
            plt.title("Cross-sectional area (CSA)")
            plt.xlabel('z (mm)')
            plt.ylabel('CSA (mm^2)')
            plt.legend([pltx, pltx_fit], ['Raw', 'Smoothed'])
            plt.show()
        # update variable
        csa = csa_smooth
    else:
        sct.printv('.. No smoothing!', verbose)

    # output volume of csa values
    sct.printv('\nCreate volume of CSA values...', verbose)
    data_csa = data_seg.astype(np.float32, copy=False)
    # loop across slices
    for iz in range(min_z_index, max_z_index+1):
        # retrieve seg pixels
        x_seg, y_seg = (data_csa[:, :, iz] > 0).nonzero()
        seg = [[x_seg[i],y_seg[i]] for i in range(0, len(x_seg))]
        # loop across pixels in segmentation
        for i in seg:
            # replace value with csa value
            data_csa[i[0], i[1], iz] = csa[iz-min_z_index]
    # replace data
    im_seg.data = data_csa
    # set original orientation
    # TODO: FIND ANOTHER WAY!!
    # im_seg.change_orientation(orientation) --> DOES NOT WORK!
    # set file name -- use .gz because faster to write
    im_seg.setFileName('csa_volume_RPI.nii.gz')
    im_seg.changeType('float32')
    # save volume
    im_seg.save()

    # output volume of csa values
    sct.printv('\nCreate volume of angle values...', verbose)
    data_angle = data_seg.astype(np.float32, copy=False)
    # loop across slices
    for iz in range(min_z_index, max_z_index + 1):
        # retrieve seg pixels
        x_seg, y_seg = (data_angle[:, :, iz] > 0).nonzero()
        seg = [[x_seg[i], y_seg[i]] for i in range(0, len(x_seg))]
        # loop across pixels in segmentation
        for i in seg:
            # replace value with csa value
            data_angle[i[0], i[1], iz] = angles[iz - min_z_index]
    # replace data
    im_seg.data = data_angle
    # set original orientation
    # TODO: FIND ANOTHER WAY!!
    # im_seg.change_orientation(orientation) --> DOES NOT WORK!
    # set file name -- use .gz because faster to write
    im_seg.setFileName('angle_volume_RPI.nii.gz')
    im_seg.changeType('float32')
    # save volume
    im_seg.save()

    # get orientation of the input data
    im_seg_original = Image('segmentation.nii.gz')
    orientation = im_seg_original.orientation
    sct.run('sct_image -i csa_volume_RPI.nii.gz -setorient '+orientation+' -o csa_volume_in_initial_orientation.nii.gz')
    sct.run('sct_image -i angle_volume_RPI.nii.gz -setorient '+orientation+' -o angle_volume_in_initial_orientation.nii.gz')

    # come back to parent folder
    os.chdir('..')

    # Generate output files
    sct.printv('\nGenerate output files...', verbose)
    sct.generate_output_file(path_tmp+'csa_volume_in_initial_orientation.nii.gz', output_folder+'csa_image.nii.gz')  # extension already included in name_output
    sct.generate_output_file(path_tmp+'angle_volume_in_initial_orientation.nii.gz', output_folder+'angle_image.nii.gz')  # extension already included in name_output
    print('\n')

    # Create output text file
    sct.printv('Display CSA per slice:', verbose)
    file_results = open(output_folder+'csa_per_slice.txt', 'w')
    file_results.write('# Slice (z),CSA (mm^2),Angle with respect to the I-S direction (degrees)\n')
    for i in range(min_z_index, max_z_index+1):
        file_results.write(str(int(i)) + ',' + str(csa[i-min_z_index])+ ',' + str(angles[i-min_z_index])+'\n')
        # Display results
        sct.printv('z = '+str(i-min_z_index)+', CSA = '+str(csa[i-min_z_index])+' mm^2'+', Angle = '+str(angles[i-min_z_index])+' deg', type='info')
    file_results.close()
    sct.printv('Save results in: '+output_folder+'csa_per_slice.txt\n', verbose)


    # average csa across vertebral levels or slices if asked (flag -z or -l)
    if slices or vert_levels:

        warning = ''
        if vert_levels and not fname_vertebral_labeling:
            sct.printv('\nERROR: You asked for specific vertebral levels (option -vert) but you did not provide any vertebral labeling file (see option -vertfile). The path to the vertebral labeling file is usually \"./label/template/PAM50_levels.nii.gz\". See usage.\n', 1, 'error')

        elif vert_levels and fname_vertebral_labeling:

            # from sct_extract_metric import get_slices_matching_with_vertebral_levels
            sct.printv('Selected vertebral levels... '+vert_levels)

            # check if vertebral labeling file exists
            sct.check_file_exist(fname_vertebral_labeling)

            # convert the vertebral labeling file to RPI orientation
            im_vertebral_labeling = set_orientation(Image(fname_vertebral_labeling), 'RPI', fname_out=path_tmp+'vertebral_labeling_RPI.nii')

            # transforming again coordinates...
            coord_voxel_centerline = im_vertebral_labeling.transfo_phys2pix([[x_centerline_fit[i], y_centerline_fit[i], z_centerline[i]] for i in range(len(z_centerline))])
            x_centerline_fit_vox = [coord[0] for coord in coord_voxel_centerline]
            y_centerline_fit_vox = [coord[1] for coord in coord_voxel_centerline]
            z_centerline_fit_vox = [coord[2] for coord in coord_voxel_centerline]

            # get the slices corresponding to the vertebral levels
            # slices, vert_levels_list, warning = get_slices_matching_with_vertebral_levels(data_seg, vert_levels, im_vertebral_labeling.data, 1)
            slices, vert_levels_list, warning = get_slices_matching_with_vertebral_levels_based_centerline(vert_levels, im_vertebral_labeling.data, x_centerline_fit_vox, y_centerline_fit_vox, z_centerline_fit_vox)

        elif not vert_levels:
            vert_levels_list = []

        # parse the selected slices
        slices_lim = slices.strip().split(':')
        slices_list = range(int(slices_lim[0]), int(slices_lim[-1])+1)
        sct.printv('Average CSA across slices '+str(slices_lim[0])+' to '+str(slices_lim[-1])+'...', type='info')

        CSA_for_selected_slices = []
        angles_for_selected_slices = []
        # Read the file csa_per_slice.txt and get the CSA for the selected slices
        with open(output_folder+'csa_per_slice.txt') as openfile:
            for line in openfile:
                if line[0] != '#':
                    line_split = line.strip().split(',')
                    if int(line_split[0]) in slices_list:
                        CSA_for_selected_slices.append(float(line_split[1]))
                        angles_for_selected_slices.append(float(line_split[2]))

        # average the CSA and angle
        mean_CSA = np.mean(np.asarray(CSA_for_selected_slices))
        std_CSA = np.std(np.asarray(CSA_for_selected_slices))
        mean_angle = np.mean(np.asarray(angles_for_selected_slices))
        std_angle = np.std(np.asarray(angles_for_selected_slices))

        sct.printv('Mean CSA: '+str(mean_CSA)+' +/- '+str(std_CSA)+' mm^2', type='info')
        sct.printv('Mean angle: '+str(mean_angle)+' +/- '+str(std_angle)+' degrees', type='info')

        # write result into output file
        save_results(output_folder+'csa_mean', overwrite, fname_segmentation, 'CSA', 'nb_voxels x px x py x cos(theta) slice-by-slice (in mm^2)', mean_CSA, std_CSA, slices, actual_vert=vert_levels_list, warning_vert_levels=warning)
        save_results(output_folder+'angle_mean', overwrite, fname_segmentation, 'Angle with respect to the I-S direction', 'Unit z vector compared to the unit tangent vector to the centerline at each slice (in degrees)', mean_angle, std_angle, slices, actual_vert=vert_levels_list, warning_vert_levels=warning)

        # compute volume between the selected slices
        sct.printv('Compute the volume in between slices '+str(slices_lim[0])+' to '+str(slices_lim[-1])+'...', type='info')
        nb_vox = np.sum(data_seg[:, :, slices_list])
        volume = nb_vox*px*py*pz
        sct.printv('Volume in between the selected slices: '+str(volume)+' mm^3', type='info')

        # write result into output file
        save_results(output_folder+'csa_volume', overwrite, fname_segmentation, 'volume', 'nb_voxels x px x py x pz (in mm^3)', volume, np.nan, slices, actual_vert=vert_levels_list, warning_vert_levels=warning)

    elif (not (slices or vert_levels)) and (overwrite == 1):
        sct.printv('WARNING: Flag \"-overwrite\" is only available if you select (a) slice(s) or (a) vertebral level(s) (flag -z or -vert) ==> CSA estimation per slice will be output in a .txt file only.', type='warning')

    # Remove temporary files
    if remove_temp_files:
        sct.printv('\nRemove temporary files...')
        sct.run('rm -rf '+path_tmp, error_exit='warning')

    # Sum up the output file names
    sct.printv('\nOutput a nifti file of CSA values along the segmentation: '+output_folder+'csa_image.nii.gz', param.verbose, 'info')
    sct.printv('Output result text file of CSA per slice: '+output_folder+'csa_per_slice.txt', param.verbose, 'info')
    if slices or vert_levels:
        sct.printv('Output result files of the mean CSA across the selected slices: \n\t\t'+output_folder+'csa_mean.txt\n\t\t'+output_folder+'csa_mean.xls\n\t\t'+output_folder+'csa_mean.pickle', param.verbose, 'info')
        sct.printv('Output result files of the volume in between the selected slices: \n\t\t'+output_folder+'csa_volume.txt\n\t\t'+output_folder+'csa_volume.xls\n\t\t'+output_folder+'csa_volume.pickle', param.verbose, 'info')

def label_vert(fname_seg, fname_label, verbose=1):
    """
    Label segmentation using vertebral labeling information
    :param fname_segmentation:
    :param fname_label:
    :param verbose:
    :return:
    """
    # Open labels
    im_disc = Image(fname_label)
    # retrieve all labels
    coord_label = im_disc.getNonZeroCoordinates()
    # compute list_disc_z and list_disc_value
    list_disc_z = []
    list_disc_value = []
    for i in range(len(coord_label)):
        list_disc_z.insert(0, coord_label[i].z)
        list_disc_value.insert(0, coord_label[i].value)
    # label segmentation
    from sct_label_vertebrae import label_segmentation
    label_segmentation(fname_seg, list_disc_z, list_disc_value, verbose=verbose)
    # Generate output files
    sct.printv('--> File created: '+sct.add_suffix(fname_seg, '_labeled.nii.gz'), verbose)


# ======================================================================================================================
# Save CSA or volume estimation in a .txt file
# ======================================================================================================================
def save_results(fname_output, overwrite, fname_data, metric_name, method, mean, std, slices_of_interest, actual_vert, warning_vert_levels):

    # define vertebral levels and slices fields
    if actual_vert:
        vertebral_levels_field = str(int(actual_vert[0])) + ' to ' + str(int(actual_vert[1]))
        if warning_vert_levels:
            for i in range(0, len(warning_vert_levels)):
                vertebral_levels_field += ' [' + str(warning_vert_levels[i]) + ']'
    else:
        if slices_of_interest != '':
            vertebral_levels_field = str(np.nan)
        else:
            vertebral_levels_field = 'ALL'

    if slices_of_interest != '':
        slices_of_interest_field = slices_of_interest
    else:
        slices_of_interest_field = 'ALL'


    sct.printv('Save results in: '+fname_output+'.txt\n')

    ## Save results in a CSV text file
    # CSV format, header lines start with "#"
    fid_metric = open(fname_output+'.txt', 'w')

    # WRITE HEADER:
    # Write date and time
    fid_metric.write('# Date - Time: '+time.strftime('%Y/%m/%d - %H:%M:%S'))
    # Write metric data file path
    fid_metric.write('\n'+'# Metric: '+metric_name)
    # Write method used for the metric estimation
    fid_metric.write('\n'+'# Calculation method: '+method)

    # Write selected vertebral levels
    fid_metric.write('\n# Vertebral levels: '+vertebral_levels_field)

    # Write selected slices
    fid_metric.write('\n'+'# Slices (z): '+slices_of_interest)

    # label headers
    fid_metric.write('%s' % ('\n'+'# File used for calculation, MEAN across slices, STDEV across slices\n\n'))

    # WRITE RESULTS
    fid_metric.write('%s, %f, %f\n' % (os.path.abspath(fname_data), mean, std))

    # Close file .txt
    fid_metric.close()


    ## Save results in a MS Excel file
    # if the user asked for no overwriting but the specified output file does not exist yet
    if (not overwrite) and (not os.path.isfile(fname_output + '.xls')):
        sct.printv('WARNING: You asked to edit the pre-existing file \"' + fname_output + '.xls\" but this file does not exist. It will be created.', type='warning')
        overwrite = 1

    if not overwrite:
        from xlrd import open_workbook
        from xlutils.copy import copy

        existing_book = open_workbook(fname_output+'.xls')

        # get index of the first empty row and leave one empty row between the two subjects
        row_index = existing_book.sheet_by_index(0).nrows

        book = copy(existing_book)
        sh = book.get_sheet(0)

    elif overwrite:
        from xlwt import Workbook

        book = Workbook()
        sh = book.add_sheet('Results', cell_overwrite_ok=True)

        # write header line
        sh.write(0, 0, 'Date - Time')
        sh.write(0, 1, 'File used for calculation')
        sh.write(0, 2, 'Metric')
        sh.write(0, 3, 'Calculation method')
        sh.write(0, 4, 'Vertebral levels')
        sh.write(0, 5, 'Slices (z)')
        sh.write(0, 6, 'MEAN across slices')
        sh.write(0, 7, 'STDEV across slices')

        row_index = 1

    # write results
    sh.write(row_index, 0, time.strftime('%Y/%m/%d - %H:%M:%S'))
    sh.write(row_index, 1, os.path.abspath(fname_data))
    sh.write(row_index, 2, metric_name)
    sh.write(row_index, 3, method)
    sh.write(row_index, 4, vertebral_levels_field)
    sh.write(row_index, 5, slices_of_interest_field)
    sh.write(row_index, 6, float(mean))
    sh.write(row_index, 7, str(std))

    book.save(fname_output+'.xls')


    ## Save results in a pickle file
    # write results in a dictionary
    output_results = {}
    output_results['Date - Time'] = time.strftime('%Y/%m/%d - %H:%M:%S')
    output_results['File used for calculation'] = os.path.abspath(fname_data)
    output_results['Metric'] = metric_name
    output_results['Calculation method'] = method
    output_results['Vertebral levels'] = vertebral_levels_field
    output_results['Slices (z)'] = slices_of_interest_field
    output_results['MEAN across slices'] = float(mean)
    output_results['STDEV across slices'] = str(std)

    # save "output_results"
    import pickle
    output_file = open(fname_output+'.pickle', 'wb')
    pickle.dump(output_results, output_file)
    output_file.close()


# ======================================================================================================================
# Find min and max slices corresponding to vertebral levels based on the fitted centerline coordinates
# ======================================================================================================================
def get_slices_matching_with_vertebral_levels_based_centerline(vertebral_levels, vertebral_labeling_data, x_centerline_fit, y_centerline_fit, z_centerline):

    # Convert the selected vertebral levels chosen into a 2-element list [start_level end_level]
    vert_levels_list = [int(x) for x in vertebral_levels.split(':')]

    # If only one vertebral level was selected (n), consider as n:n
    if len(vert_levels_list) == 1:
        vert_levels_list = [vert_levels_list[0], vert_levels_list[0]]

    # Check if there are only two values [start_level, end_level] and if the end level is higher than the start level
    if (len(vert_levels_list) > 2) or (vert_levels_list[0] > vert_levels_list[1]):
        sct.printv('\nERROR:  "' + vertebral_levels + '" is not correct. Enter format "1:4". Exit program.\n', type='error')

    # Extract the vertebral levels available in the metric image
    vertebral_levels_available = np.array(list(set(vertebral_labeling_data[vertebral_labeling_data > 0])))

    # Check if the vertebral levels selected are available
    warning=[]  # list of strings gathering the potential following warning(s) to be written in the output .txt file
    min_vert_level_available = min(vertebral_levels_available)  # lowest vertebral level available
    max_vert_level_available = max(vertebral_levels_available)  # highest vertebral level available

    if vert_levels_list[0] < min_vert_level_available:
        vert_levels_list[0] = min_vert_level_available
        warning.append('WARNING: the bottom vertebral level you selected is lower to the lowest level available --> '
                       'Selected the lowest vertebral level available: ' + str(int(vert_levels_list[0])))  # record the
                       # warning to write it later in the .txt output file
        sct.printv('WARNING: the bottom vertebral level you selected is lower to the lowest ' \
                                          'level available \n--> Selected the lowest vertebral level available: '+\
              str(int(vert_levels_list[0])), type='warning')

    if vert_levels_list[1] > max_vert_level_available:
        vert_levels_list[1] = max_vert_level_available
        warning.append('WARNING: the top vertebral level you selected is higher to the highest level available --> '
                       'Selected the highest vertebral level available: ' + str(int(vert_levels_list[1])))  # record the
        # warning to write it later in the .txt output file

        sct.printv('WARNING: the top vertebral level you selected is higher to the highest ' \
                                          'level available \n--> Selected the highest vertebral level available: ' + \
              str(int(vert_levels_list[1])), type='warning')

    if vert_levels_list[0] not in vertebral_levels_available:
        distance = vertebral_levels_available - vert_levels_list[0]  # relative distance
        distance_min_among_negative_value = min(abs(distance[distance < 0]))  # minimal distance among the negative
        # relative distances
        vert_levels_list[0] = vertebral_levels_available[distance == distance_min_among_negative_value]  # element
        # of the initial list corresponding to this minimal distance
        warning.append('WARNING: the bottom vertebral level you selected is not available --> Selected the nearest '
                       'inferior level available: ' + str(int(vert_levels_list[0])))
        sct.printv('WARNING: the bottom vertebral level you selected is not available \n--> Selected the ' \
                             'nearest inferior level available: '+str(int(vert_levels_list[0])), type='warning')  # record the
        # warning to write it later in the .txt output file

    if vert_levels_list[1] not in vertebral_levels_available:
        distance = vertebral_levels_available - vert_levels_list[1]  # relative distance
        distance_min_among_positive_value = min(abs(distance[distance > 0]))  # minimal distance among the negative
        # relative distances
        vert_levels_list[1] = vertebral_levels_available[distance == distance_min_among_positive_value]  # element
        # of the initial list corresponding to this minimal distance
        warning.append('WARNING: the top vertebral level you selected is not available --> Selected the nearest superior'
                       ' level available: ' + str(int(vert_levels_list[1])))  # record the warning to write it later in the .txt output file

        sct.printv('WARNING: the top vertebral level you selected is not available \n--> Selected the ' \
                             'nearest superior level available: ' + str(int(vert_levels_list[1])), type='warning')

    # Find slices included in the vertebral levels wanted by the user
    sct.printv('\tFind slices corresponding to vertebral levels based on the centerline...')
    nz = len(z_centerline)
    matching_slices_centerline_vert_labeling = []
    for i_z in range(0, nz):
        # if the centerline is in the vertebral levels asked by the user, record the slice number
        if vertebral_labeling_data[np.round(x_centerline_fit[i_z]), np.round(y_centerline_fit[i_z]), z_centerline[i_z]] in range(vert_levels_list[0], vert_levels_list[1]+1):
            matching_slices_centerline_vert_labeling.append(z_centerline[i_z])

    # now, find the min and max slices that are included in the vertebral levels
    slices = str(min(matching_slices_centerline_vert_labeling))+':'+str(max(matching_slices_centerline_vert_labeling))
    sct.printv('\t'+slices)

    return slices, vert_levels_list, warning

#=======================================================================================================================
# b_spline_centerline
#=======================================================================================================================
def b_spline_centerline(x_centerline,y_centerline,z_centerline):
                          
    print '\nFitting centerline using B-spline approximation...'
    points = [[x_centerline[n],y_centerline[n],z_centerline[n]] for n in range(len(x_centerline))]
    nurbs = NURBS(3,3000,points)  # BE very careful with the spline order that you choose : if order is too high ( > 4 or 5) you need to set a higher number of Control Points (cf sct_nurbs ). For the third argument (number of points), give at least len(z_centerline)+500 or higher
                          
    P = nurbs.getCourbe3D()
    x_centerline_fit=P[0]
    y_centerline_fit=P[1]
    Q = nurbs.getCourbe3D_deriv()
    x_centerline_deriv=Q[0]
    y_centerline_deriv=Q[1]
    z_centerline_deriv=Q[2]
                          
    return x_centerline_fit, y_centerline_fit,x_centerline_deriv,y_centerline_deriv,z_centerline_deriv


#=======================================================================================================================
# Normalization
#=======================================================================================================================
def normalize(vect):
    norm=np.linalg.norm(vect)
    return vect/norm


#=======================================================================================================================
# Ellipse fitting for a set of data
#=======================================================================================================================
#http://nicky.vanforeest.com/misc/fitEllipse/fitEllipse.html
def Ellipse_fit(x,y):
    x = x[:,np.newaxis]
    y = y[:,np.newaxis]
    D =  np.hstack((x*x, x*y, y*y, x, y, np.ones_like(x)))
    S = np.dot(D.T,D)
    C = np.zeros([6,6])
    C[0,2] = C[2,0] = 2
    C[1,1] = -1
    E, V =  np.linalg.eig(np.dot(np.linalg.inv(S), C))
    n = np.argmax(np.abs(E))
    a = V[:,n]
    return a


#=======================================================================================================================
# Getting a and b parameter for fitted ellipse
#=======================================================================================================================
def ellipse_dim(a):
    b,c,d,f,g,a = a[1]/2, a[2], a[3]/2, a[4]/2, a[5], a[0]
    up = 2*(a*f*f+c*d*d+g*b*b-2*b*d*f-a*c*g)
    down1=(b*b-a*c)*( (c-a)*np.sqrt(1+4*b*b/((a-c)*(a-c)))-(c+a))
    down2=(b*b-a*c)*( (a-c)*np.sqrt(1+4*b*b/((a-c)*(a-c)))-(c+a))
    res1=np.sqrt(up/down1)
    res2=np.sqrt(up/down2)
    return np.array([res1, res2])


#=======================================================================================================================
# Detect edges of an image
#=======================================================================================================================
def edge_detection(f):

    import Image
    
    #sigma = 1.0
    img = Image.open(f) #grayscale
    imgdata = np.array(img, dtype = float)
    G = imgdata
    #G = ndi.filters.gaussian_filter(imgdata, sigma)
    gradx = np.array(G, dtype = float)
    grady = np.array(G, dtype = float)
 
    mask_x = np.array([[-1,0,1],[-2,0,2],[-1,0,1]])
          
    mask_y = np.array([[1,2,1],[0,0,0],[-1,-2,-1]])
 
    width = img.size[1]
    height = img.size[0]
 
    for i in range(1, width-1):
        for j in range(1, height-1):
        
            px = np.sum(mask_x*G[(i-1):(i+1)+1,(j-1):(j+1)+1])
            py = np.sum(mask_y*G[(i-1):(i+1)+1,(j-1):(j+1)+1])
            gradx[i][j] = px
            grady[i][j] = py

    mag = scipy.hypot(gradx,grady)

    treshold = np.max(mag)*0.9

    for i in range(width):
        for j in range(height):
            if mag[i][j]>treshold:
                mag[i][j]=1
            else:
                mag[i][j] = 0
   
    return mag



# START PROGRAM
# =========================================================================================
if __name__ == "__main__":
    # initialize parameters
    param = Param()
    param_default = Param()
    # call main function
    main(sys.argv[1:])
