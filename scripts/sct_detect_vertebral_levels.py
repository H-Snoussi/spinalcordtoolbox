#!/usr/bin/env python
#########################################################################################
#
# Detect vertebral levels from centerline.
#
# ---------------------------------------------------------------------------------------
# Copyright (c) 2013 Polytechnique Montreal <www.neuro.polymtl.ca>
# Authors: Eugenie Ullmann, Karun Raju, Tanguy Duval, Julien Cohen-Adad
#
# About the license: see the file LICENSE.TXT
#########################################################################################

# TODO: add user input option (show sagittal slice)
# TODO: make better distance template

# from msct_base_classes import BaseScript
import sys
from os import chdir
from time import strftime

import numpy as np

from sct_utils import extract_fname, printv, run, generate_output_file, slash_at_the_end
from msct_parser import Parser
from msct_image import Image


class Param:
    def __init__(self):
        self.verbose = '1'
        self.remove_tmp_files = '1'


# PARSER
# ==========================================================================================
def get_parser():
    # parser initialisation
    parser = Parser(__file__)
    parser.usage.set_description('''This program automatically detect the spinal cord in a MR image and output a centerline of the spinal cord.''')
    parser.add_option(name="-i",
                      type_value="file",
                      description="input image.",
                      mandatory=True,
                      example="t2.nii.gz")
    parser.add_option(name="-seg",
                      type_value="file",
                      description="Segmentation or centerline of the spinal cord.",
                      mandatory=True,
                      example="t2_seg.nii.gz")
    parser.add_option(name="-initz",
                      type_value=[[','], 'int'],
                      description='Initialize labeling by providing slice number (in superior-inferior direction!!) and disc value. Value corresponds to vertebral level above disc (e.g., for C3/C4 disc, value=3). Separate with ","',
                      mandatory=False,
                      example=['125,3'])
    parser.add_option(name="-initcenter",
                      type_value='int',
                      description='Initialize labeling by providing the disc value centered in the rostro-caudal direction. If the spine is curved, then consider the disc that projects onto the cord at the center of the z-FOV',
                      mandatory=False)
    parser.add_option(name='-o',
                      type_value='file_output',
                      description='Output file',
                      mandatory=False,
                      default_value='',
                      example='t2_seg_labeled.nii.gz')
    parser.add_option(name="-r",
                      type_value="multiple_choice",
                      description="Remove temporary files.",
                      mandatory=False,
                      default_value=param.remove_tmp_files,
                      example=['0', '1'])
    parser.add_option(name="-v",
                      type_value="multiple_choice",
                      description="""Verbose. 0: nothing. 1: basic. 2: extended.""",
                      mandatory=False,
                      default_value=param.verbose,
                      example=['0', '1', '2'])
    parser.add_option(name="-h",
                      type_value=None,
                      description="display this help",
                      mandatory=False)
    return parser


# MAIN
# ==========================================================================================
def main(args=None):

    # initializations
    initz = ''
    initcenter = ''

    # check user arguments
    if not args:
        args = sys.argv[1:]

    # Get parser info
    parser = get_parser()
    arguments = parser.parse(sys.argv[1:])
    fname_in = arguments["-i"]
    fname_seg = arguments['-seg']
    # contrast = arguments['-t']
    if '-o' in arguments:
        fname_out = arguments["-o"]
    else:
        fname_out = ''
    if '-initz' in arguments:
        initz = arguments['-initz']
    if '-initcenter' in arguments:
        initcenter = arguments['-initcenter']
    param.verbose = int(arguments['-v'])
    param.remove_tmp_files = int(arguments['-r'])

    # # create temporary folder
    # printv('\nCreate temporary folder...', param.verbose)
    # path_tmp = slash_at_the_end('tmp.'+strftime("%y%m%d%H%M%S"), 1)
    # run('mkdir '+path_tmp, param.verbose)
    #
    # # Copying input data to tmp folder
    # printv('\nCopying input data to tmp folder...', param.verbose)
    # run('sct_convert -i '+fname_in+' -o '+path_tmp+'data.nii')
    # run('sct_convert -i '+fname_seg+' -o '+path_tmp+'segmentation.nii.gz')

    # Go go temp folder
    path_tmp = '/Users/julien/data/biospective/20150914/test/processing/t2/tmp.150915091711/'
    chdir(path_tmp)

    # create label to identify disc
    printv('\nCreate label to identify disc...', param.verbose)
    if initz:
        create_label_z('segmentation.nii.gz', initz[0], initz[1])  # create label located at z_center
    elif initcenter:
        # find z centered in FOV
        nii = Image('segmentation.nii.gz')
        nii.change_orientation('RPI')  # reorient to RPI
        nx, ny, nz, nt, px, py, pz, pt = nii.dim  # Get dimensions
        z_center = int(round(nz/2))  # get z_center
        create_label_z('segmentation.nii.gz', z_center, initcenter)  # create label located at z_center

    # TODO: denoise data

    # # Straighten spinal cord
    # printv('\nStraighten spinal cord...', param.verbose)
    # run('sct_straighten_spinalcord -i data.nii -c segmentation.nii.gz')
    #
    # # Apply straightening to segmentation
    # # N.B. Output is RPI
    # printv('\nApply straightening to segmentation...', param.verbose)
    # run('sct_apply_transfo -i segmentation.nii.gz -d data_straight.nii -w warp_curve2straight.nii.gz -o segmentation_straight.nii.gz -x linear')
    # # Threshold segmentation to 0.5
    # run('sct_maths -i segmentation_straight.nii.gz -thr 0.5 -o segmentation_straight.nii.gz')
    #
    # # Apply straightening to z-label
    # printv('\nDilate z-label and apply straightening...', param.verbose)
    # run('sct_apply_transfo -i labelz.nii.gz -d data_straight.nii -w warp_curve2straight.nii.gz -o labelz_straight.nii.gz -x nn')

    # get z value and disk value to initialize labeling
    printv('\nGet z and disc values from straight label...', param.verbose)
    init_disc = get_z_and_disc_values_from_label('labelz_straight.nii.gz')
    printv('.. '+str(init_disc), param.verbose)

    # detect vertebral levels on straight spinal cord
    printv('\nDetect inter-vertebral discs and label vertebral levels...', param.verbose)
    vertebral_detection('data_straight.nii', 'segmentation_straight.nii.gz', init_disc)

    # un-straighten spinal cord
    printv('\nUn-straighten labeling...', param.verbose)
    run('sct_apply_transfo -i segmentation_straight_labeled.nii.gz -d segmentation.nii.gz -w warp_straight2curve.nii.gz -o segmentation_labeled.nii.gz -x nn')

    # clean labeled segmentation
    # TODO: (i) find missing voxels wrt. original segmentation, and attribute value closest to neighboring label and (ii) remove additional voxels.

    # Build fname_out
    if fname_out == '':
        path_seg, file_seg, ext_seg = extract_fname(fname_seg)
        fname_out = path_seg+file_seg+'_labeled'+ext_seg

    # come back to parent folder
    chdir('..')

    # Generate output files
    printv('\nGenerate output files...', param.verbose)
    generate_output_file(path_tmp+'segmentation_labeled.nii.gz', fname_out)

    # Remove temporary files
    if param.remove_tmp_files == 1:
        printv('\nRemove temporary files...', param.verbose)
        run('rm -rf '+path_tmp)

    # to view results
    printv('\nDone! To view results, type:', param.verbose)
    printv('fslview '+fname_in+' '+fname_out+' &\n', param.verbose, 'info')



# Detect vertebral levels
# ==========================================================================================
def vertebral_detection(fname, fname_seg, init_disc):

    from scipy.signal import argrelextrema

    shift_AP = 17  # shift the centerline towards the spine (in mm).
    size_AP = 5  # window size in AP direction (=y) in mm
    size_RL = 7  # window size in RL direction (=x) in mm
    size_IS = 7  # window size in RL direction (=z) in mm
    searching_window_for_maximum = 5  # size used for finding local maxima
    thr_corr = 0.3  # disc correlation threshold. Below this value, use template distance.
    verbose = param.verbose
    # define mean distance between adjacent discs: C1/C2 -> C2/C3, C2/C3 -> C4/C5, ..., L1/L2 -> L2/L3.
    mean_distance = np.array([18, 16, 18.0000, 16.0000, 15.1667, 15.3333, 15.8333,   18.1667,   18.6667,   18.6667,
    19.8333,   20.6667,   21.6667,   22.3333,   23.8333,   24.1667,   26.0000,   28.6667,   30.5000,   33.5000,
    33.0000,   31.3330])


    if verbose == 2:
        import matplotlib.pyplot as plt
        plt.ion()  # enables interactive mode

    # open anatomical volume
    img = Image(fname)
    data = img.data
    # get dimension
    nx, ny, nz, nt, px, py, pz, pt = img.dim

    # matshow(img.data[:, :, 100]), show()

    #==================================================
    # Compute intensity profile across vertebrae
    #==================================================

    shift_AP = shift_AP * py
    size_AP = size_AP * py
    size_RL = size_RL * px

    # define z: vector of indices along spine
    z = range(nz)
    # define xc and yc (centered in the field of view)
    xc = round(nx/2)  # direction RL
    yc = round(ny/2)  # direction AP

    if verbose == 2:
        # plt.figure(1), plt.imshow(np.mean(data[xc-7:xc+7, :, :], axis=0).transpose(), cmap=plt.cm.gray, origin='lower'), plt.title('Anatomical image'), plt.draw()
        plt.matshow(np.mean(data[xc-7:xc+7, :, :], axis=0).transpose(), fignum=1, cmap=plt.cm.gray, origin='lower'), plt.title('Anatomical image'), plt.draw()
        # plt.matshow(np.flipud(np.mean(data[xc-7:xc+7, :, :], axis=0).transpose()), fignum=1, cmap=plt.cm.gray), plt.title('Anatomical image'), plt.draw()
        # display init disc
        plt.autoscale(enable=False)  # to prevent autoscale of axis when displaying plot
        plt.figure(1), plt.scatter(yc+shift_AP, init_disc[0], c='y', s=50), plt.draw()
        plt.text(yc+shift_AP+4, init_disc[0], str(init_disc[1])+'/'+str(init_disc[1]+1), verticalalignment='center', horizontalalignment='left', color='yellow', fontsize=15)
        # plt.axis('off')


    # FIND DISCS
    # ===========================================================================
    list_disc_z = []
    list_disc_value = []
    # adjust to pix size
    mean_distance = mean_distance * pz
    mean_distance_real = np.zeros(len(mean_distance))
    # search peaks along z direction
    current_z = init_disc[0]
    current_disc = init_disc[1]
    # append initial position to main list
    list_disc_z = np.append(list_disc_z, current_z).astype(int)
    list_disc_value = np.append(list_disc_value, current_disc).astype(int)
    direction = 'superior'
    # define mean distance to next disc
    approx_distance_to_next_disc = int(round(mean_distance[current_disc]))
    # find_disc(data, current_z, current_disc, approx_distance_to_next_disc, direction)
    # loop until potential new peak is inside of FOV
    search_next_disc = True
    while search_next_disc:
        printv('Current disc: '+str(current_disc)+' (z='+str(current_z)+'). Direction: '+direction, verbose)
        # Get pattern centered at z = current_z
        pattern = data[xc-size_RL:xc+size_RL+1, yc+shift_AP-size_AP:yc+shift_AP+size_AP+1, current_z-size_IS:current_z+size_IS+1]
        pattern1d = pattern.ravel()
        # pattern2d = np.mean(data[xc-size_RL:xc+size_RL+1, yc+shift_AP-size_AP:yc+shift_AP+size_AP+1, current_z-size_IS:current_z+size_IS+1], axis=0)
        if verbose == 2:
            plt.matshow(np.flipud(np.mean(pattern[:, :, :], axis=0).transpose()), cmap=plt.cm.gray), plt.title('Pattern in sagittal averaged across R-L'), plt.draw()
        # compute correlation between pattern and data within range of z defined by template distance
        length_z_corr = approx_distance_to_next_disc * 2
        I_corr = np.zeros((length_z_corr, 1))
        ind_I = 0
        for iz in range(length_z_corr):
            if direction == 'superior':
                data_chunk3d = data[xc-size_RL:xc+size_RL+1, yc+shift_AP-size_AP:yc+shift_AP+size_AP+1, current_z+iz-size_IS:current_z+iz+size_IS+1]
                # if part of the data is missing, calculate size of missing data.
                padding_size = pattern.shape[2] - data_chunk3d.shape[2]
                # pad data with zeros
                data_chunk3d = np.pad(data_chunk3d, ((0, 0), (0, 0), (0, padding_size)), 'constant', constant_values=0)
            elif direction == 'inferior':
                data_chunk3d = data[xc-size_RL:xc+size_RL+1, yc+shift_AP-size_AP:yc+shift_AP+size_AP+1, current_z-iz-size_IS:current_z-iz+size_IS+1]
                # if part of the data is missing, calculate size of missing data.
                padding_size = pattern.shape[2] - data_chunk3d.shape[2]
                # pad data with zeros
                data_chunk3d = np.pad(data_chunk3d, ((0, 0), (0, 0), (padding_size, 0)), 'constant', constant_values=0)
            # plt.matshow(np.flipud(np.mean(data_chunk3d, axis=0).transpose()), cmap=plt.cm.gray), plt.title('Data chunk averaged across R-L'), plt.draw(), plt.savefig('datachunk_disc'+str(current_disc)+'iz'+str(iz))
            data_chunk1d = data_chunk3d.ravel()
            # check if data_chunk1d contains at least one non-zero value
            if np.any(data_chunk1d):
                I_corr[ind_I] = np.corrcoef(data_chunk1d, pattern1d)[0, 1]
            else:
                printv('.. WARNING: Data only contains zero. Set correlation to 0.', verbose)
            ind_I = ind_I + 1

        if verbose == 2:
            plt.figure(), plt.plot(I_corr), plt.title('Correlation of pattern with data.'), plt.draw()

        # Find peak within local neighborhood defined by mean distance template
        ind_peak = argrelextrema(I_corr, np.greater, order=searching_window_for_maximum)[0]
        if len(ind_peak) == 0:
            printv('.. WARNING: No peak found. Using adjusted template distance.', verbose)
            ind_peak = approx_distance_to_next_disc
        else:
            # keep peak with maximum correlation
            ind_peak = ind_peak[np.argmax(I_corr[ind_peak])]
            # check if correlation is high enough
            if I_corr[ind_peak] < thr_corr:
                printv('.. WARNING: Correlation is too low. Using adjusted template distance.', verbose)
                ind_peak = approx_distance_to_next_disc
            else:
                printv('.. Peak found: '+str(ind_peak)+' (correlation = '+str(I_corr[ind_peak][0])+')', verbose)

        # display peak
        if verbose == 2:
            plt.plot(ind_peak, I_corr[ind_peak], 'ro'), plt.draw()

        # assign new z_start and disc value
        if direction == 'superior':
            current_z = current_z + int(ind_peak)
            current_disc = current_disc - 1
        elif direction == 'inferior':
            current_z = current_z - int(ind_peak)
            current_disc = current_disc + 1

        # display new disc
        if verbose == 2:
            plt.figure(1), plt.scatter(yc+shift_AP, current_z, c='r', s=50), plt.draw()
            plt.text(yc+shift_AP+4, current_z, str(current_disc)+'/'+str(current_disc+1), verticalalignment='center', horizontalalignment='left', color='red', fontsize=15), plt.draw()

        # append to main list
        if direction == 'superior':
            # append at the end
            list_disc_z = np.append(list_disc_z, current_z)
            list_disc_value = np.append(list_disc_value, current_disc)
        elif direction == 'inferior':
            # append at the beginning
            list_disc_z = np.append(current_z, list_disc_z)
            list_disc_value = np.append(current_disc, list_disc_value)

        # compute real distance between adjacent discs
        # for indexing: starts at list_disc_value[1:], which corresponds to max disc-1
        mean_distance_real[list_disc_value[1:]-1] = np.diff(list_disc_z)
        # compute correcting factor between real distances and template
        ind_distances = np.nonzero(mean_distance_real)[0]
        correcting_factor = np.mean( mean_distance_real[ind_distances] / mean_distance[ind_distances])
        printv('.. correcting factor: '+str(correcting_factor), verbose)
        # compute approximate distance to next disc using template adjusted from previous real distances
        mean_distance_adjusted = mean_distance * correcting_factor

        # define mean distance to next disc
        if current_disc == 1:
            printv('.. Cannot go above disc 1.', verbose)
        else:
            if direction == 'superior':
                approx_distance_to_next_disc = int(round(mean_distance_adjusted[current_disc-2]))
            elif direction == 'inferior':
                approx_distance_to_next_disc = int(round(mean_distance_adjusted[current_disc-1]))
            printv('.. approximate distance to next disc: '+str(approx_distance_to_next_disc)+' mm', verbose)

        # if current_z is larger than searching zone, switch direction (and start from initial z)
        if current_z + approx_distance_to_next_disc >= nz or current_disc == 1:
            printv('.. Switching to inferior direction.', verbose)
            direction = 'inferior'
            current_z = init_disc[0]
            current_disc = init_disc[1]
            # need to recalculate approximate distance to next disc
            approx_distance_to_next_disc = int(round(mean_distance_adjusted[current_disc-1]))
            printv('.. recalculating approximate distance to next disc: '+str(approx_distance_to_next_disc)+' mm', verbose)
        # if current_z is lower than searching zone, stop searching
        if current_z - approx_distance_to_next_disc <= 0:
            search_next_disc = False

    if verbose == 2:
        # save figure with labels
        plt.figure(1), plt.savefig('anat_straight_with_labels.png')

    # # sort list_disc_z and list_disc_value
    # list_disc_z = np.array(sorted(list_disc_z, reverse=True))
    # list_disc_value.sort()

    # if upper disc is not 1, add disc above top disc based on mean_distance_adjusted
    upper_disc = min(list_disc_value) - 1
    if not upper_disc == 1:
        printv('Adding top disc based on adjusted template distance: #'+str(upper_disc), verbose)
        approx_distance_to_next_disc = int(round(mean_distance_adjusted[upper_disc-1]))
        next_z = max(list_disc_z) + approx_distance_to_next_disc
        printv('.. approximate distance: '+str(approx_distance_to_next_disc)+' mm', verbose)
        # make sure next disc does not go beyond FOV in superior direction
        if next_z > nz:
            list_disc_z = np.append(list_disc_z, nz)
        else:
            list_disc_z = np.append(list_disc_z, next_z)
        # assign disc value
        list_disc_value = np.append(list_disc_value, upper_disc)

    # LABEL SEGMENTATION
    # open segmentation
    seg = Image(fname_seg)
    for iz in range(nz):
        # get index of the disk above iz
        ind_above_iz = np.nonzero((list_disc_z-iz).clip(0))[0]
        if not ind_above_iz.size:
            # if ind_above_iz is empty, attribute value 0
            # vertebral_level = np.min(labeled_peaks)
            vertebral_level = 0
        else:
            # ind_disk_above = np.where(peaks-iz > 0)[0][0]
            ind_disk_above = min(ind_above_iz)
            # assign vertebral level (add one because iz is BELOW the disk)
            vertebral_level = list_disc_value[ind_disk_above] + 1
            # print vertebral_level
        # get voxels in mask
        ind_nonzero = np.nonzero(seg.data[:, :, iz])
        seg.data[ind_nonzero[0], ind_nonzero[1], iz] = vertebral_level

    # WRITE LABELED SEGMENTATION
    seg.file_name += '_labeled'
    seg.save()


# Create label
# ==========================================================================================
def create_label_z(fname_seg, z, value):
    """
    Create a label at coordinates x_center, y_center, z
    :param fname_seg: segmentation
    :param z: int
    :return: fname_label
    """
    fname_label = 'labelz.nii.gz'
    nii = Image(fname_seg)
    orientation_origin = nii.change_orientation('RPI')  # change orientation to RPI
    nx, ny, nz, nt, px, py, pz, pt = nii.dim  # Get dimensions
    # find x and y coordinates of the centerline at z using center of mass
    from scipy.ndimage.measurements import center_of_mass
    x, y = center_of_mass(nii.data[:, :, z])
    x, y = int(round(x)), int(round(y))
    nii.data[:, :, :] = 0
    nii.data[x, y, z] = value
    # dilate label to prevent it from disappearing due to nearestneighbor interpolation
    from sct_maths import dilate
    nii.data = dilate(nii.data, 3) * value  # multiplies by value because output of dilation is binary
    nii.setFileName(fname_label)
    nii.change_orientation(orientation_origin)  # put back in original orientation
    nii.save()
    return fname_label


# Get z and label value
# ==========================================================================================
def get_z_and_disc_values_from_label(fname_label):
    """
    Find z-value and label-value based on labeled image
    :param fname_label: image that contains label
    :return: [z_label, value_label] int list
    """
    nii = Image(fname_label)
    # get center of mass of label
    from scipy.ndimage.measurements import center_of_mass
    x_label, y_label, z_label = center_of_mass(nii.data)
    x_label, y_label, z_label = int(round(x_label)), int(round(y_label)), int(round(z_label))
    # get label value
    value_label = int(nii.data[x_label, y_label, z_label])
    return [z_label, value_label]


# START PROGRAM
# ==========================================================================================
if __name__ == "__main__":
    # # initialize parameters
    param = Param()
    # call main function
    main()
