# --------------------------------------------------------
# Fast R-CNN
# Copyright (c) 2015 Microsoft
# Licensed under The MIT License [see LICENSE for details]
# Written by Ross Girshick
#
# Modified by Peng Tang for OICR
#
# Modified by Satoshi Kosugi for OBJECT-AWARE-INSTANCE-LABELING
# --------------------------------------------------------

"""Compute minibatch blobs for training a OICR network."""

import numpy as np
import numpy.random as npr
import cv2
from fast_rcnn.config import cfg
from utils.blob import prep_im_for_blob, im_list_to_blob
import os

def get_minibatch(roidb, num_classes, saliency_masked=False):
    """Given a roidb, construct a minibatch sampled from it."""
    num_images = len(roidb)
    assert num_images == 1, 'batch size should equal to 1!'
    # Sample random scales to use for each image in this batch
    random_scale_inds = npr.randint(0, high=len(cfg.TRAIN.SCALES),
                                    size=num_images)

    # Get the input image blob, formatted for caffe
    im_blob, im_scales, im_shapes = _get_image_blob(roidb, random_scale_inds, saliency_masked)

    # Now, build the region of interest and label blobs
    rois_blob = np.zeros((0, 5), dtype=np.float32)
    labels_blob = np.zeros((0, 20), dtype=np.float32)
    flg_blob = np.zeros((0, 20), dtype=np.float32)

    for im_i in xrange(num_images):
        labels, im_rois, flg = _sample_rois(roidb[im_i], num_classes)

        # Add to RoIs blob
        rois = _project_im_rois(im_rois, im_scales[im_i])
        batch_ind = im_i * np.ones((rois.shape[0], 1))
        rois_blob_this_image = np.hstack((batch_ind, rois))

        if cfg.DEDUP_BOXES > 0:
            v = np.array([1, 1e3, 1e6, 1e9, 1e12])
            hashes = np.round(rois_blob_this_image * cfg.DEDUP_BOXES).dot(v)
            _, index, inv_index = np.unique(hashes, return_index=True,
                                            return_inverse=True)
            rois_blob_this_image = rois_blob_this_image[index, :]

        rois_blob = np.vstack((rois_blob, rois_blob_this_image))
        if flg is not None:
            flg_blob = np.vstack((flg_blob, flg[index]))

        # Add to labels blobs
        labels_blob = np.vstack((labels_blob, labels))

    if saliency_masked:
        labels_blob = np.tile(labels_blob, (rois_blob.shape[0], 1))

    if flg is None:
        blobs = {'data': im_blob,
                 'rois': rois_blob,
                 'labels': labels_blob}
    else:
        blobs = {'data': im_blob,
                 'rois': rois_blob,
                 'labels': labels_blob,
                 'flg': flg_blob}

    return blobs

def _sample_rois(roidb, num_classes):
    """Generate a random sample of RoIs comprising foreground and background
    examples.
    """
    labels = roidb['labels']
    rois = roidb['boxes']
    num_rois = len(rois)

    keep_inds = npr.choice(num_rois, size=num_rois, replace=False)
    rois = rois[keep_inds]

    if "flg" in roidb.keys():
        flg = roidb['flg'][keep_inds]
    else:
        flg = None

    return labels, rois, flg

def _get_image_blob(roidb, scale_inds, saliency_masked):
    """Builds an input blob from the images in the roidb at the specified
    scales.
    """
    num_images = len(roidb)
    processed_ims = []
    im_scales = []
    im_shapes = np.zeros((0, 2), dtype=np.float32)
    for i in xrange(num_images):
        im = cv2.imread(roidb[i]['image'])
        if saliency_masked:
            im = mask_with_saliency(im, roidb[i]['image'], roidb[i]['saliency_dir'])
        if roidb[i]['flipped']:
            im = im[:, ::-1, :]
        target_size = cfg.TRAIN.SCALES[scale_inds[i]]
        im, im_scale, im_shape = prep_im_for_blob(im, cfg.PIXEL_MEANS,
                                                  target_size,
                                                  cfg.TRAIN.MAX_SIZE)
        im_scales.append(im_scale)
        processed_ims.append(im)
        im_shapes = np.vstack((im_shapes, im_shape))

    # Create a blob to hold the input images
    blob = im_list_to_blob(processed_ims)

    return blob, im_scales, im_shapes

def _project_im_rois(im_rois, im_scale_factor):
    """Project image RoIs into the rescaled training image."""
    rois = im_rois * im_scale_factor
    return rois

def mask_with_saliency(im, im_name, saliency_dir):
    saliency_map_name = os.path.join(saliency_dir, im_name.split("/")[-1].replace("jpg", "png"))

    saliency_map = cv2.imread(saliency_map_name)
    assert saliency_map is not None, "Cannot load saliency map"

    im = im - cfg.PIXEL_MEANS
    im[saliency_map <= cfg.TRAIN.SALIENCY_THRESH] = 0
    im = im + cfg.PIXEL_MEANS
    return im
