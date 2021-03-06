#!/usr/bin/env python

import settings
import images

import numpy as np
import subprocess
import sys
import os
import socket


# Segment uses the bounding box identified by the sharpest image in a
# set of stacks to chop just the edf into individual images

# Started on 3/21/2014 by Yusu Liu
# code uses base code of PM Hull (20-Oct-13) with updates by B. Dobbins, PMH, and Y. Liu
# converted to python and updated by K. Nelson (2015-Oct)


def segment(settings_file):

    version = '2016-7-12'

    print "Loading settings from %s..." % settings_file
    runs = settings.parse(settings_file)

    for i, run in enumerate(runs):

        print('Segment - running configuration %d of %d from %s'
              % (i+1, len(runs), settings_file))

        # Get list of images in directory
        image_list = images.list_files(run['directory'], run['input_ext'])

        # Set up additonal run parameters
        run['image_file_label'] = 'th=%05.4f_size=%04.0fu-%04.0fu' % (run['threshold'],
                                                                      run['minimum_size'],
                                                                      run['maximum_size'])

        run['image_label'] = contruct_image_label(run, version)

        if not os.path.exists(run['full_output']):
            os.makedirs(run['full_output'])

        top_image_filename = image_list[-1]
        objects, _ = setup_object_boxes(top_image_filename, run)

        if run['mode'] == 'final':

            # sanity check to avoid creating unnecessary file
            if len(objects) > 10000:
                sys.exit('Over 10,000 objects are identified in the image, are you sure you want to continue?')

            print('Saving Settings into %s' % run['full_output'])
            settings.save(run.copy())

            # last plane in some image samples is not a true focus plane
            if run['skip_last_plane']:
                final_list = image_list[:-1]
            else:
                final_list = image_list

            # Loop over the planes we're interested in, load an image, then process it
            for plane_num, plane_image_filename in enumerate(final_list):

                final(plane_image_filename, objects, run, plane_num)


def get_git_version():

    gitproc = subprocess.Popen(['git', 'show-ref'], stdout=subprocess.PIPE)
    (stdout, stderr) = gitproc.communicate()

    for row in stdout.split('\n'):
        if row.find('HEAD') != -1:
            hash = row.split()[0]
            break

    return hash


def setup_object_boxes(image_filename, run):

        # Load and resize top-level image
        image = images.load(image_filename, run)

        # Identify all objects based on threshold and size values
        print 'INFO: Finding objects'
        objects = images.find_objects(image, run)

        print 'INFO: Saving overview image'
        images.save_overview_image(image, objects, image_filename, run)

        return objects, image


def final(orig_filename, box_list, run, plane_num, image=None):

    if image is None:
        image = images.load(orig_filename, run)

    image_size = np.shape(image)   # [width, height]

    for box_num, box in enumerate(box_list):

        # crop expects [x1, y1, x2, y2], box is [y1, x1, y2, x2]
        crop_box = [box[1], box[0], box[3], box[2]]
        width = crop_box[2] - crop_box[0]
        height = crop_box[3] - crop_box[1]
        image_subsample = images.crop(image, crop_box)

        x_percent = float(crop_box[0]) / float(image_size[1]) * 100
        y_percent = float(crop_box[1]) / float(image_size[0]) * 100

        description = 'Object #%05d of %05d ( %d x %d pixels at slide position %05.2f x %05.2f )' \
                      % (box_num+1, len(box_list), width, height, x_percent, y_percent)

        labeled_image_subsample, label = images.label_image(image_subsample, orig_filename,
                                                            description, run)

        object_directory = '%s%s%s_obj%05d' % (run['full_output'], os.sep, run['unique_id'], box_num+1)
        if not os.path.exists(object_directory):
            os.makedirs(object_directory)

        print object_directory
        output_filename = '%s%s%s_obj%05d_plane%03d.%s' % (object_directory, os.sep,
                                                           run['unique_id'], box_num+1, plane_num,
                                                           run['output_ext'])

        tags = images.add_comment(output_filename, '. '.join(label))
        print output_filename
        images.save(labeled_image_subsample, output_filename, tags=tags)


def contruct_image_label(run, version):

    catalog_number = 'None'
    if run['catalog_prefix']:
        if 'IP' in run['unique_id']:  # Special fix for Yale
            catalog_number = run['catalog_prefix']+' '+run['unique_id'].split('.')[1]
        else:
            catalog_number = run['catalog_prefix']+' '+run['unique_id']

    text = []
    text.append('%4.2f %s per pixel | Age and Source:  %s from %s'
                % (run['units_per_pixel'], run['unit'], run['age'], run['source']))
    this_line = 'Processed at '+run['location']

    if run['author']:
        this_line += ' by '+run['author']
    this_line += ' (Catalog Number: %s)' % catalog_number

    text.append(this_line)
    text.append('CODE VERSION: %s, PROCESSED ON: %s' % (version, run['timestamp']))
    text.append('Threshold of %4.2f and size filter of %d - %d %s'
                % (run['threshold'], run['minimum_size'], run['maximum_size'], run['unit']))
    text.append('Directory: %s' % run['subdirectory'])

    return text

if __name__ == "__main__":

    if socket.gethostname() == 'tide.geology.yale.edu':
        os.nice(10)

    if len(sys.argv) == 2:
        segment(sys.argv[1])

    else:
        print 'Usage: segment <settings_file>'
        sys.exit('Error: incorrect usage')
