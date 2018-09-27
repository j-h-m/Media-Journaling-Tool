# =============================================================================
# Authors: PAR Government
# Organization: DARPA
#
# Copyright (c) 2016 PAR Government
# All rights reserved.
#==============================================================================


"""
MAINTAIN RULES FOR VALIDATION (as referened in the operation.json's rules definition).
MAINTAIN RULES FOR PROJECT PROPERTIES and FINAL NODE PROPERTIES
(as referenced in the property defintion if project_properties.json)
"""
from software_loader import  getProjectProperties, getRule,getOperations
from tool_set import  openImageFile, fileTypeChanged, fileType, \
    getMilliSecondsAndFrameCount, toIntTuple, differenceBetweenFrame, differenceBetweeMillisecondsAndFrame, \
    getDurationStringFromMilliseconds, getFileMeta,  openImage, getMilliSeconds,isCompressed,\
    deserializeMatrix,isHomographyOk,composeCloneMask
from support import getValue,setPathValue
from graph_meta_tools import MetaDataExtractor
from maskgen.video_tools import get_frame_rate
from maskgen import graph_meta_tools

import numpy
from image_graph import ImageGraph
import os
import exif
import logging
from video_tools import getMaskSetForEntireVideo, get_frame_count, get_duration
from ffmpeg_api import get_meta_from_video
import numpy as np
from maskgen.validation.core import Severity

project_property_rules = {}

def missing_donor_inputmask(edge, dir):
    return (('inputmaskname' not in edge or \
             edge['inputmaskname'] is None or \
             len(edge['inputmaskname']) == 0 or
             not os.path.exists(os.path.join(dir, edge['inputmaskname']))) and \
            (edge['op'] == 'PasteSampled' and \
                getValue(edge,'arguments.purpose') == 'clone') or
            edge['op'] == 'TransformMove')

def eligible_donor_inputmask(edge):
    """
    Is the edge eligible to provide a donor
    :param edge:
    :return:
    """
    return ('inputmaskname' in edge and \
            edge['inputmaskname'] is not None and \
            len(edge['inputmaskname']) > 0 and \
            edge['op'] == 'PasteSampled' and \
            getValue(edge,'arguments.purpose') == 'clone')



def eligible_for_donor(edge):
    return edge['op'] == 'Donor' or eligible_donor_inputmask(edge)

def rotationCheck(op, graph, frm, to):
    """
    :param op:
    :param graph:
    :param frm:
    :param to:
    :return:
    @type op: Operation
    @type graph: ImageGraph
    @type frm: str
    @type to: str
    """
    edge = graph.get_edge(frm, to)
    args = edge['arguments'] if 'arguments' in edge  else {}
    frm_img = graph.get_image(frm)[0]
    to_img = graph.get_image(to)[0]
    diff_frm = frm_img.size[0] - frm_img.size[1]
    diff_to = to_img.size[0] - to_img.size[1]
    rotated = 'Image Rotated' in args and args['Image Rotated'] == 'yes'
    orientation = getValue(edge, 'exifdiff.Orientation')
    if orientation is not None:
        orientation = str(orientation)
        if '270' in orientation or '90' in orientation:
            if rotated and frm_img.size == to_img.size and frm_img.size[0] != frm_img.size[1]:
                return (Severity.ERROR,'Image was not rotated as stated by the parameter Image Rotated')
    if not rotated and numpy.sign(diff_frm) != numpy.sign(diff_to):
        return (Severity.ERROR,'Image was rotated. Parameter Image Rotated is set to "no"')
    return None

def checkUncompressed(op, graph, frm, to):
    file = os.path.join(graph.dir, graph.get_node(frm)['file'])
    if os.path.exists(file) and \
        isCompressed(file):
            return (Severity.WARNING, 'Starting node appears to be compressed')

def checkFrameTimeAlignment(op,graph, frm, to):
    """
    :param op:
    :param graph:
    :param frm:
    :param to:
    :return:
    @type op: Operation
    @type graph: ImageGraph
    @type frm: str
    @type to: str
    """
    edge = graph.get_edge(frm, to)
    args = edge['arguments'] if 'arguments' in edge  else {}
    st = None
    et = None
    for k, v in args.iteritems():
        if k.endswith('End Time'):
            et = v
        elif k.endswith('Start Time'):
            st = v
    masks = edge['videomasks'] if 'videomasks' in edge else []
    mask_start_constraints = {}
    mask_end_constraints = {}
    mask_rates = {}
    extractor = MetaDataExtractor(graph)
    file = extractor.getNodeFile(frm)
    if fileType(file) not in ['audio','video']:
        return
    real_masks = getMaskSetForEntireVideo(extractor.getMetaDataLocator(frm),start_time=st, end_time=et,
                                          media_types=['video','audio'])
    if real_masks is None:
        return
    for mask in masks:
        startid = 'starttime' if mask['type'] == 'audio' else 'startframe'
        endid = 'endtime' if mask['type'] == 'audio' else 'endframe'
        mask_start_constraints[ mask['type']] = min(
            (mask_start_constraints[mask['type']] if mask['type'] in mask_start_constraints else 2147483647),
                                                   mask[startid])
        #mask_rates[ mask['type']] = mask['rate'] if 'rate' in mask else getFrameRate(file,
        #                                                                             default=29.97,
        #                                                                             audio= mask['type']=='audio')
        mask_end_constraints[mask['type']] = max(
            (mask_end_constraints[mask['type']] if mask['type'] in mask_end_constraints else 0),
            mask[endid])
    real_mask_start_constraints = {}
    real_mask_end_constraints = {}
    for mask in real_masks:
        startid = 'starttime' if mask['type'] == 'audio' else 'startframe'
        endid = 'endtime' if mask['type'] == 'audio' else 'endframe'
        real_mask_start_constraints[mask['type']] = min(
            (real_mask_start_constraints[mask['type']] if mask['type'] in real_mask_start_constraints else 2147483647),
            mask[startid])
       # mask_rates[mask['type']] = mask['rate'] if 'rate' in mask  and mask['type'] not in mask_rates else \
        #    getFrameRate(file, default=29.97 ,audio= mask['type']=='audio')
        real_mask_end_constraints[mask['type']] = max(
            (real_mask_end_constraints[mask['type']] if mask['type'] in real_mask_end_constraints else 0),
            mask[endid])
    if st is not None and len(masks) == 0:
        return (Severity.ERROR,'Change masks not generated.  Trying recomputing edge mask')
    mask_rates['video'] = 1.0
    mask_rates['audio'] = 100.0
    for key, value in mask_start_constraints.iteritems():
        if key in mask_start_constraints and abs(value - mask_start_constraints[key]) >  mask_rates[key]:
            if key == 'audio':
                return (Severity.WARNING,'Start time entered does not match detected start time: {}'.format(
                    getDurationStringFromMilliseconds(mask_start_constraints[key])))
            else:
                return (Severity.WARNING, 'Start frame entered does not match detected start frame: {}'.format(
                    mask_start_constraints[key]))
    for key, value in real_mask_end_constraints.iteritems():
        if key in mask_end_constraints and abs(value - mask_end_constraints[key]) > mask_rates[key]:
            if key == 'audio':
                return (Severity.WARNING,'End time entered does not match detected end time: {}'.format(
                    getDurationStringFromMilliseconds(mask_end_constraints[key])))
            else:
                return (Severity.WARNING, 'End frame entered does not match detected end frame: {}'.format(
                    mask_end_constraints[key]))


def checkVideoMasks(op,graph, frm, to):
    """
    :param op:
    :param graph:
    :param frm:
    :param to:
    :return:
    @type op: Operation
    @type graph: ImageGraph
    @type frm: str
    @type to: str
    """
    node = graph.get_node(to)
    if 'filetype' not in node or node['filetype'] != 'video':
        return
    edge = graph.get_edge(frm, to)
    if 'videomasks' not in edge or edge['videomasks'] is None or \
                    len(edge['videomasks']) == 0:
        return (Severity.ERROR,'Edge missing video masks')


def checkAddFrameTime(op, graph, frm, to):
    """
    :param op:
    :param graph:
    :param frm:
    :param to:
    :return:
    @type op: Operation
    @type graph: ImageGraph
    @type frm: str
    @type to: str
    """
    edge = graph.get_edge(frm, to)
    args = edge['arguments'] if 'arguments' in edge  else {}
    st = None
    for k, v in args.iteritems():
        if k.endswith('Start Time') or  k.endswith('Insertion Time') or k.endswith('Insertion Start Time'):
            st = v
    masks = edge['videomasks'] if 'videomasks' in edge else []
    mask_start_constraints = {}
    mask_rates = {}
    extractor = MetaDataExtractor(graph)
    filename = extractor.getNodeFile(frm)
    if fileType(filename) not in ['audio','video']:
        return
    real_masks = getMaskSetForEntireVideo(extractor.getMetaDataLocator(frm),start_time=st,media_types=['video','audio'])
    for mask in masks:
        startid = 'starttime' if mask['type']  == 'audio' else 'startframe'
        mask_start_constraints[ mask['type']] = min(
            (mask_start_constraints[mask['type']] if mask['type'] in mask_start_constraints else 2147483647),
                                                   mask[startid])
        #mask_rates[ mask['type']] = mask['rate'] if 'rate' in mask else getFrameRate(file,
        #                                                                             default=29.97,
        #                                                                             audio= mask['type']=='audio')
    real_mask_start_constraints = {}
    for mask in real_masks:
        startid = 'starttime' if mask['type'] == 'audio' else 'startframe'
        real_mask_start_constraints[mask['type']] = min(
            (real_mask_start_constraints[mask['type']] if mask['type'] in real_mask_start_constraints else 2147483647),
            mask[startid])
        #mask_rates[mask['type']] = mask['rate'] if 'rate' in mask  and mask['type'] not in mask_rates else \
        #    getFrameRate(file, default=29.97 ,audio= mask['type']=='audio')
    if st is not None and len(masks) == 0:
        return (Severity.ERROR,'Change masks not generated.  Trying recomputing edge mask')
    mask_rates['video'] = 1.0
    mask_rates['audio'] = 100.0
    for key, value in mask_start_constraints.iteritems():
        if key in mask_start_constraints and abs(value - mask_start_constraints[key]) >  mask_rates[key]:
            if key == 'audio':
                return (Severity.WARNING,'Insertion time entered does not match detected start time: {}'.format(
                    getDurationStringFromMilliseconds(mask_start_constraints[key])))
            else:
                return (Severity.WARNING, 'Insertion time entered does not match detected start frame: {}'.format(
                    mask_start_constraints[key]))


def checkMetaDate(op, graph, frm, to):
    """
      :param op:
      :param graph:
      :param frm:
      :param to:
      :return:
      @type op: Operation
       @type graph: ImageGraph
      @type frm: str
      @type to: str
      """
    import re
    edge = graph.get_edge(frm, to)
    diff = getValue(edge,'exifdiff',{})
    for k,v in diff.iteritems():
        if 'Date' in k and v[0] == 'change':
            if re.sub('[0-9a-zA-Z]','x',v[1]) != re.sub('[0-9a-zA-Z]','x',v[2]):
                return (Severity.WARNING, 'Meta Data {} Date Format Changed: {}'.format(k, v[2]))

def checkFrameTimes(op, graph, frm, to):
    """
    :param op:
    :param graph:
    :param frm:
    :param to:
    :return:
    @type op: Operation
     @type graph: ImageGraph
    @type frm: str
    @type to: str
    """
    edge = graph.get_edge(frm, to)
    args = edge['arguments'] if 'arguments' in edge  else {}
    st = None
    et = None
    for k, v in args.iteritems():
        if k.endswith('End Time'):
            et = getMilliSecondsAndFrameCount(v)
        elif k.endswith('Start Time'):
            st = getMilliSecondsAndFrameCount(v, defaultValue=(0,1))
    if et is None:
        return None
    st = st if st is not None else (0, 1)
    if st[0] > et[0] or (st[0] == et[0] and st[1] > et[1] and st[1] > 0):
        return (Severity.ERROR,'Start Time occurs after End Time')
    return None

def checkFrameRateChange_Strict(op, graph, frm, to):
    if checkFrameRateChange(op, graph, frm, to):
        return (Severity.ERROR, 'Frame Rate Changed between nodes')

def checkFrameRateChange_Lenient(op, graph, frm, to):
    if checkFrameRateChange(op, graph, frm, to):
        return (Severity.WARNING, 'Frame Rate Changed between nodes')

def checkFrameRateChange(op, graph, frm, to):
    """

    :param op: Operation
    :param graph: ImageGraph
    :param frm: str
    :param to: str
    :return:
    """
    extractor = MetaDataExtractor(graph)
    from_rate = get_frame_rate(extractor.getMetaDataLocator(frm), audio=op.category == 'Audio',default=0)
    to_rate = get_frame_rate(extractor.getMetaDataLocator(to),audio=op.category == 'Audio', default=0)
    if from_rate is not None and to_rate is not None and abs(from_rate - to_rate) > 0.001:
        return True
    return False


def checkCropLength(op, graph, frm, to):
    """
    :param op:
    :param graph:
    :param frm:
    :param to:
    :return:
    @type op: Operation
     @type graph: ImageGraph
    @type frm: str
    @type to: str
    """
    edge = graph.get_edge(frm, to)
    args = edge['arguments'] if 'arguments' in edge  else {}
    st = None
    et = None
    for k, v in args.iteritems():
        if k.endswith('Start Time'):
            st = getMilliSecondsAndFrameCount(v, defaultValue=(0,0))
        elif k.endswith('End Time'):
            et = getMilliSecondsAndFrameCount(v, defaultValue=(0,0))
    if st is None and et is None:
        return None
    st = st if st is not None else (0, 0)
    et = et if et is not None else (0, 0)
    if 'metadatadiff' not in edge:
        return (Severity.ERROR,'Edge missing change data.  Recompute Mask.')
    extractor = MetaDataExtractor(graph)
    locator = extractor.getMetaDataLocator(to)
    file = os.path.join(graph.dir, graph.get_node(to)['file'])
    if fileType(file) == 'audio':
        rate = get_frame_rate(locator, default=44000, audio=True)
        givenDifference = differenceBetweeMillisecondsAndFrame(et, st, rate)
        duration_to = get_duration(locator, audio=True)
        if abs(duration_to - givenDifference) > 100:
            return (Severity.ERROR, 'Actual amount of cropped frames in milliseconds is {} '.format(duration_to))
        return None
    else:
        set = getMaskSetForEntireVideo(locator, media_types=['video'])
        if not set:
            return (Severity.ERROR, 'Video channel not found in {} '.format(locator.get_filename))
        givenDifference = differenceBetweenFrame(et, st, getValue(set,'rate',29.97))
        duration = getValue(set[0],'frames',0)
        if abs(duration - givenDifference) > 1:
            return (Severity.ERROR,'Actual amount of frames of cropped video is {}'.format(duration))
    return None

def checkCutFrames(op, graph, frm, to):
    """
    :param op:
    :param graph:
    :param frm:
    :param to:
    :return:
    @type op: Operation
     @type graph: ImageGraph
    @type frm: str
    @type to: str
    """
    extractor = MetaDataExtractor(graph)
    for media_type in ['video','audio']:
        to_masks = getMaskSetForEntireVideo(extractor.getMetaDataLocator(to), media_types=[media_type])
        frm_masks = getMaskSetForEntireVideo(extractor.getMetaDataLocator(frm), media_types=[media_type])
        recordedMasks = extractor.getMasksFromEdge(frm, to, [media_type])
        recorded_change = sum([i['frames'] for i in recordedMasks if i['type'] == media_type])
        diff = frm_masks[0]['frames'] - to_masks[0]['frames']
        if diff != recorded_change:
            if media_type == 'video':
                return (Severity.ERROR, 'Actual amount of frames of cut video is {}'.format(diff))
            elif abs(diff - recorded_change) > frm_masks[0]['rate']*0.1:
                millis = diff * 1000.0/frm_masks[0]['rate']
                return (Severity.ERROR, 'Actual amount of cut time in milliseconds is {} '.format(millis))

def checkCropSize(op, graph, frm, to):
    """
    :param op:
    :param graph:
    :param frm:
    :param to:
    :return:
    @type op: Operation
    @type graph: ImageGraph
    @type frm: str
    @type to: str
    """
    edge = graph.get_edge(frm, to)
    if 'shape change' in edge:
        changeTuple = toIntTuple(edge['shape change'])
        if changeTuple[0] > 0 or changeTuple[1] > 0:
            return (Severity.ERROR,'Crop cannot increase a dimension size of the image')


def checkResizeInterpolation(op, graph, frm, to):
    """
    :param op:
    :param graph:
    :param frm:
    :param to:
    :return:
    @type op: Operation
    @type graph: ImageGraph
    @type frm: str
    @type to: str
    """
    edge = graph.get_edge(frm, to)
    interpolation = getValue(edge,'arguments.interpolation','')
    if 'shape change' in edge:
        changeTuple = toIntTuple(edge['shape change'])
        sizeChange = (changeTuple[0], changeTuple[1])
        if (sizeChange[0] < 0 or sizeChange[1] < 0) and 'none' in interpolation:
            return (Severity.ERROR,interpolation + ' interpolation is not permitted with a decrease in size')


def checkChannelLoss(op, graph, frm, to):
    """
     :param op:
     :param graph:
     :param frm:
     :param to:
     :return:
     @type op: Operation
     @type graph: ImageGraph
     @type frm: str
     @type to: str
    """
    vidBefore = graph.get_image_path(frm)
    vidAfter = graph.get_image_path(to)
    if fileType(vidAfter) == 'image' or fileType(vidBefore) == 'image':
        return
    metaBefore = getFileMeta(vidBefore)
    metaAfter = getFileMeta(vidAfter)
    if len(metaBefore) > len(metaAfter):
        return (Severity.WARNING,'change in the number of streams occurred')

def checkEmpty(op,graph, frm, to):
    edge = graph.get_edge(frm, to)
    if getValue(edge, 'empty mask')  == 'yes':
        return (Severity.ERROR,"An empty change mask indicating an manipulation did not occur.")

def checkSameChannels(op, graph, frm, to):
    """
     :param op:
     :param graph:
     :param frm:
     :param to:
     :return:
     @type op: Operation
     @type graph: ImageGraph
     @type frm: str
     @type to: str
    """
    vidBefore = graph.get_image_path(frm)
    vidAfter = graph.get_image_path(to)
    if fileType(vidAfter) == 'image' or fileType(vidBefore) == 'image':
        return
    metaAfter = getFileMeta(vidAfter)
    if fileType(vidBefore).startswith('zip') and len(metaAfter) != 1:
        return (Severity.WARNING,'change in the number of streams occurred')
    metaBefore = getFileMeta(vidBefore)
    if len(metaBefore) != len(metaAfter):
        return (Severity.WARNING,'change in the number of streams occurred')
    if len(metaBefore) == 0:
        return (Severity.ERROR,'streams are not detected or missing')

def checkHasVideoChannel(op,graph, frm, to):
    """
     :param op:
     :param graph:
     :param frm:
     :param to:
     :return:
     @type op: Operation
     @type graph: ImageGraph
     @type frm: str
     @type to: str
    """
    vid = graph.get_image_path(to)
    meta = getFileMeta(vid)
    if 'video' not in meta:
        return (Severity.ERROR,'video channel missing in file')


def checkAudioChannels(op,graph, frm, to):
    """
     :param op:
     :param graph:
     :param frm:
     :param to:
     :return:
     @type op: Operation
     @type graph: ImageGraph
     @type frm: str
     @type to: str
    """
    vid = graph.get_image_path(to)
    meta = getFileMeta(vid)
    if 'audio' not in meta:
        return (Severity.ERROR,'audio channel not present')

def checkAudioSameorLonger(op, graph,frm, to):
    edge = graph.get_edge(frm, to)
    if edge['arguments']['add type'] == 'insert':
        return checkAudioLengthBigger(op, graph, frm, to)
    return checkAudioLength(op, graph, frm, to)


def checkAudioLengthBigger(op, graph, frm, to):
    edge = graph.get_edge(frm, to)
    nStreams = ["video", "unknown", "data"]
    try:
        streams = getValue(edge, 'metadatadiff[0]').keys()
        for s in streams:
            streamOption, change = s.split(":")[0], s.split(":")[1]
            if streamOption not in nStreams and change == "duration":
                change = getValue(edge, 'metadatadiff[0]')[s]
                if int(change[1]) < int(change[2]):
                    return None
        return (Severity.ERROR, "Audio is not longer in duration")
    except:
        return (Severity.ERROR, "Audio is not longer in duration")

def checkAudioLengthSmaller(op, graph, frm, to):
    edge = graph.get_edge(frm, to)
    nStreams = ["video", "unknown", "data"]

    try:
        streams = getValue(edge, 'metadatadiff[0]').keys()
        for s in streams:
            streamOption, change = s.split(":")[0], s.split(":")[1]
            if streamOption not in nStreams and change == "duration":
                change = getValue(edge, 'metadatadiff[0]')[s]
                if int(change[1]) > int(change[2]):
                    return None
        return (Severity.ERROR, "Audio is not shorter in duration")
    except:
        return (Severity.ERROR, "Audio is not shorter in duration")



def checkAudioLength(op, graph, frm, to):
    edge = graph.get_edge(frm, to)
    nStreams = ["video", "unknown", "data"]

    try:
        streams = getValue(edge, 'metadatadiff[0]').keys()
        for s in streams:
            streamOption, change = s.split(":")[0], s.split(":")[1]
            if streamOption not in nStreams and change == "duration":
               return (Severity.ERROR, "Audio duration does not match")
        return None
    except:
        return None


def checkFileTypeChangeForDonor(op, graph, frm, to):
    """
     :param op:
     :param graph:
     :param frm:
     :param to:
     :return:
     @type op: Operation
     @type graph: ImageGraph
     @type frm: str
     @type to: str
    """
    frm_file = graph.get_image(frm)[1]
    to_file = graph.get_image(to)[1]
    if fileTypeChanged(to_file, frm_file):
        predecessors = graph.predecessors(to)
        if len(predecessors) < 2:
            return (Severity.ERROR,'donor image missing')
        for pred in predecessors:
            edge = graph.get_edge(pred, to)
            if edge['op'] == 'Donor':
                donor_file = graph.get_image(pred)[1]
                if fileTypeChanged(donor_file, to_file):
                    return (Severity.ERROR,'operation not permitted to change the type of image or video file')
    return None


def checkFileTypeChange(op, graph, frm, to):
    """
     :param op:
     :param graph:
     :param frm:
     :param to:
     :return:
     @type op: Operation
     @type graph: ImageGraph
     @type frm: str
     @type to: str
    """
    frm_file = graph.get_image(frm)[1]
    to_file = graph.get_image(to)[1]
    if fileTypeChanged(to_file, frm_file):
        return (Severity.ERROR,'operation not permitted to change the type of image or video file')
    return None

def serial_corr(wave, lag=1):
    n = len(wave)
    y1 = wave[lag:]
    y2 = wave[:n - lag]
    corr = np.corrcoef(y1, y2, ddof=0)[0, 1]
    return corr


def autocorr(wave):
    lags = range(len(wave) // 2)
    corrs = [serial_corr(wave, lag) for lag in lags]
    return lags, corrs


def checkLevelsVsCurves(op, graph, frm, to):
    """
     :param op:
     :param graph:
     :param frm:
     :param to:
     :return:
     @type op: Operation
     @type graph: ImageGraph
     @type frm: str
     @type to: str
    """
    edge = graph.get_edge(frm, to)
    frm_file = graph.get_image(frm)[0].convert('L').to_array()
    to_file = graph.get_image(to)[0].convert('L').to_array()
    rangebins = range(257)
    lstart = np.histogram(frm_file, bins=rangebins)
    lfinish = np.histogram(to_file, bins=rangebins)
    diff = lstart[0] - lfinish[0]
    # change = lstart[0]/lfinish[0].astype('float')
    # cor(diff[-len(diff)], diff[-1])
    lags, corrs1 = autocorr(diff)
    # lags, corrs2 = autocorr(change)
    # deviation = np.std(np.diff(change))
    # regr = linear_model.LinearRegression()
    # Train the model using the training sets
    # regr.fit(np.asarray(, )
    # print ("%s %f %f" % (edge['op'], corrs1[1],deviation))
    # np.var(np.diff(x))
    # print("Mean squared error: %.2f" % np.mean( sigmoid(np.asarray(rangebins[:-1]),*popt)- diff.reshape(256, 1) ** 2))

    # The lag-one autocorrelation will serve as a score and has a reasonably straightforward statistical interpretation too.
    if corrs1[1] < 0.9:
        return (Severity.WARNING,'Verify this operation was performed with Levels rather than Curves')
    return None


def checkForRawFile(op, graph, frm, to):
    """
     :param op:
     :param graph:
     :param frm:
     :param to:
     :return:
     @type op: Operation
     @type graph: ImageGraph
     @type frm: str
     @type to: str
    """
    snode = graph.get_node(frm)
    exifdata = exif.getexif(os.path.join(graph.dir, snode['file']))
    if 'File Type' in exifdata and exifdata['File Type'] in ['AA', 'AAX', 'ACR',
                                                             'AI', 'AIT', 'AFM', 'ACFM', 'AMFM',
                                                             'PDF', 'PS', 'AVI',
                                                             'APE', 'ASF', 'BMP', 'DIB'
                                                                                  'BPG', 'PNG', 'JPEG', 'GIF',
                                                             'DIVX', 'DOC', 'DOCX',
                                                             'DV', 'EXV',
                                                             'F4V', 'F4A', 'F4P', 'F4B',
                                                             'EXR', 'HDR', 'FLV', 'FPF', 'FLAC',
                                                             'FLA', 'FFF', 'IDML',
                                                             'J2C', 'JPC', 'JP2', 'JPF',
                                                             'J2K', 'JPX', 'JPM',
                                                             'JPE', 'JPG',
                                                             'LA', 'LFP',
                                                             'MP4', 'MP3',
                                                             'M2TS', 'MTS', 'M2T', 'TS',
                                                             'M4A', 'M4B', 'M4P', 'M4V',
                                                             'MAX', 'MOV', 'QT',
                                                             'O', 'PAC', 'MIFF', 'MIF',
                                                             'MIE',
                                                             'JNG', 'MNG', 'PPT', 'PPS',
                                                             'QIF', 'QTI', 'QTIF',
                                                             'RIF', 'RIFF', 'SWF',
                                                             'VOB', 'TTF', 'TTC', 'SWF',
                                                             'SEQ', 'WEBM', 'WEBP']:
        return (Severity.ERROR,'Only raw images permitted for this operation')
    return None


def check_pastemask(op,graph, frm, to):
    """
     :param op:
     :param graph:
     :param frm:
     :param to:
     :return:
     @type op: Operation
     @type graph: ImageGraph
     @type frm: str
     @type to: str
    """
    edge = graph.get_edge(frm, to)
    if 'arguments' in edge and edge['arguments'] is not None and 'pastemask' in edge['arguments']:
        from_img, from_file = graph.get_image(frm)
        file = os.path.join(graph.dir, edge['arguments']['pastemask'])
        if not os.path.exists(file):
            return (Severity.ERROR,'Pastemask file is missing')
        pasteim = openImageFile(file)
        if pasteim.size != from_img.size:
            return (Severity.ERROR,'Pastemask image does not match the size of the source image')
    return None


def check_local_warn(op, graph, frm, to):
    """
     :param op:
     :param graph:
     :param frm:
     :param to:
     :return:
     @type op: Operation
     @type graph: ImageGraph
     @type frm: str
     @type to: str
    """
    edge = graph.get_edge(frm, to)
    included_in_composite = 'recordMaskInComposite' in edge and edge['recordMaskInComposite'] == 'yes'
    is_global = 'global' in edge and edge['global'] == 'yes'
    if not is_global and not included_in_composite and op.category not in ['Output', 'AntiForensic','Laundering','PostProcessing']:
        return (Severity.WARNING, 'Operation link appears to affect local area in the image; should be included in the composite mask')
    return None

def check_dirty_mask(op, graph, frm, to):
    edge = graph.get_edge(frm, to)
    if getValue( edge,'empty mask','yes') == 'no':
        return (Severity.ERROR, 'This type of operation should produce a clean mask.  Side effects occurred.')

def sampledInputMask(op,graph, frm, to):
    """
         :param op:
         :param graph:
         :param frm:
         :param to:
         :return:
         @type op: Operation
         @type graph: ImageGraph
         @type frm: str
         @type to: str
    """
    edge = graph.get_edge(frm, to)
    if 'arguments' in edge and \
            ('purpose' not in edge['arguments'] or
             edge['arguments']['purpose'] not in ['clone', 'stacking']) and \
                    'inputmaskname' in edge and \
                    edge['inputmaskname'] is not None:
        edge.pop('inputmaskname')
        return (Severity.WARNING,'Un-needed input mask. Auto-removal executed.')
    return None


def addToComposite(graph, start, end):
    edge = graph.get_edge(start, end)
    edge['recordMaskInComposite'] = 'yes'

def check_local(op, graph, frm, to):
    """
         :param op:
         :param graph:
         :param frm:
         :param to:
         :return:
         @type op: Operation
         @type graph: ImageGraph
         @type frm: str
         @type to: str
    """
    edge = graph.get_edge(frm, to)
    included_in_composite = 'recordMaskInComposite' in edge and edge['recordMaskInComposite'] == 'yes'
    is_global = 'global' in edge and edge['global'] == 'yes'
    if not is_global and not included_in_composite:
        return (Severity.ERROR,'Operation link appears affect local area in the image and should be included in the composite mask',addToComposite)
    return None


def check_eight_bit(op, graph, frm, to):
    """
         :param op:
         :param graph:
         :param frm:
         :param to:
         :return:
         @type op: Operation
         @type graph: ImageGraph
         @type frm: str
         @type to: str
    """
    from_img, from_file = graph.get_image(frm)
    to_img, to_file = graph.get_image(to)
    if from_img.size != to_img.size and \
            to_file.lower().endswith('jpg') and \
            (to_img.size[0] % 8 > 0 or to_img.size[1] % 8 > 0):
        return (Severity.WARNING,'JPEG image size is not aligned to 8x8 pixels')
    return None


def getDonor(graph, node):
    predecessors = graph.predecessors(node)
    if len(predecessors) < 2:
        return None
    for pred in predecessors:
        edge = graph.get_edge(pred, node)
        if edge['op'] == 'Donor':
            return (pred, edge)
    return None


def checkForDonorWithRegion(op, graph, frm, to):
    """
         :param op:
         :param graph:
         :param frm:
         :param to:
         :return:
         @type op: Operation
         @type graph: ImageGraph
         @type frm: str
         @type to: str
    """
    pred = graph.predecessors(to)
    if len(pred) < 2:
        return (Severity.ERROR,'donor image missing')
    donor = pred[0] if pred[1] == frm else pred[1]
    edge = graph.get_edge(frm, to)
    if 'arguments' in edge and edge['arguments'] and \
                    'purpose' in edge['arguments'] and edge['arguments']['purpose'] == 'blend':
        return None
    if not graph.findOp(donor, 'SelectRegion'):
        return (Severity.WARNING, 'SelectRegion missing on path to donor')
    return None


def checkForDonor(op, graph, frm, to):
    """
         :param op:
         :param graph:
         :param frm:
         :param to:
         :return:
         @type op: Operation
         @type graph: ImageGraph
         @type frm: str
         @type to: str
    """
    pred = graph.predecessors(to)
    if len(pred) < 2:
        return (Severity.ERROR, 'donor image/video missing')
    return None


def checkForDonorAudio(op, graph, frm, to):
    """
         :param op:
         :param graph:
         :param frm:
         :param to:
         :return:
         @type op: Operation
         @type graph: ImageGraph
         @type frm: str
         @type to: str
    """
    edge = graph.get_edge(frm, to)
    args = edge['arguments'] if 'arguments' in edge else {}
    if 'Direct from PC' in args and args['Direct from PC'] == 'yes':
        return None
    pred = graph.predecessors(to)
    if len(pred) < 2:
        return (Severity.WARNING,'donor image/video missing')
    return None

def checkAudioOnly(op, graph, frm, to):
    edge = graph.get_edge(frm, to)
    diffs = getValue(edge, 'metadatadiff[0]')
    frames = getValue(diffs,'video:nb_frames')
    if  frames is not None:
        return  (Severity.ERROR,"Length of video has changed")

def checkAudioAdd(op, graph, frm, to):
    edge = graph.get_edge(frm, to)
    if getValue(edge,'arguments.add type','insert') == 'insert':
        if checkDurationAudio(op, graph, frm, to) is None:
            return (Severity.ERROR, "Length of video did not change even though insert is appled")

def checkLengthSame(op, graph, frm, to):
    """
     the length of video should not change
     :param op:
     :param graph:
     :param frm:
     :param to:
     :return:
     @type op: Operation
     @type graph: ImageGraph
     @type frm: str
     @type to: str
    """
    edge = graph.get_edge(frm, to)
    durationChangeTuple = getValue(edge, 'metadatadiff[0].video:nb_frames')
    if durationChangeTuple is not None and durationChangeTuple[0] == 'change':
        return (Severity.WARNING,"Length of video has changed")

def checkAudioTimeFormat(op, graph, frm, to):
    edge = graph.get_edge(frm, to)
    st = getValue(edge, 'arguments.Start Time','00:00:00')
    et = getValue(edge, 'arguments.End Time', '00:00:00')
    if getMilliSecondsAndFrameCount(et, defaultValue=(0,0))[1] > 1:
        return (Severity.ERROR,"End Time should not include frame number")
    if getMilliSecondsAndFrameCount(st, defaultValue=(0,0))[1] > 1:
        return (Severity.ERROR,"Start Time should not include frame number")

def checkOverlay(op, graph, frm, to):
    edge = graph.get_edge(frm, to)
    if getValue(edge,'arguments.add type') in ['overlay','replace']:
        return checkDurationAudio(op, graph, frm, to)

def checkForSelectFrames(op, graph, frm, to):
    """
         :param op:
         :param graph:
         :param frm:
         :param to:
         :return:
         @type op: Operation
         @type graph: ImageGraph
         @type frm: str
         @type to: str
    """
    pred = graph.predecessors(to)
    if len(pred) < 2:
        return (Severity.ERROR,'donor image missing')
    donor = pred[0] if pred[1] == frm else pred[1]
    if not graph.findOp(donor, 'SelectRegionFromFrames'):
        return (Severity.WARNING, 'SelectRegionFromFrames missing on path to donor')
    return None

def checkDurationAudio(op, graph, frm, to):
    """
         :param op:
         :param graph:
         :param frm:
         :param to:
         :return:
         @type op: Operation
         @type graph: ImageGraph
         @type frm: str
         @type to: str
    """
    extractor = MetaDataExtractor(graph)
    fm = get_duration(extractor.getMetaDataLocator(frm),audio=True)
    tm = get_duration(extractor.getMetaDataLocator(to),audio=True)
    if fm is not None and abs(fm-tm)>100:
        return (Severity.ERROR,"Duration of media changed")

def checkLengthSmaller(op, graph, frm, to):
    """
         :param op:
         :param graph:
         :param frm:
         :param to:
         :return:
         @type op: Operation
         @type graph: ImageGraph
         @type frm: str
         @type to: str
    """
    edge = graph.get_edge(frm, to)
    durationChangeTuple = getValue(edge, 'metadatadiff[0].video:nb_frames')
    if durationChangeTuple is None or \
            (durationChangeTuple[0] == 'change' and \
                         getMilliSecondsAndFrameCount(durationChangeTuple[1], defaultValue=(0,1))[0] <
                         getMilliSecondsAndFrameCount(durationChangeTuple[2], defaultValue=(0,1))[0]):
        return (Severity.ERROR,"Length of video is not shorter")


def checkResolution(op, graph, frm, to):
    """
     :param op:
     :param graph:
     :param frm:
     :param to:
     :return:
     @type op: Operation
     @type graph: ImageGraph
     @type frm: str
     @type to: str
    """
    edge = graph.get_edge(frm, to)
    width = getValue(edge, 'metadatadiff[0].video:width')
    height = getValue(edge, 'metadatadiff[0].video:height')
    resolution = getValue(edge, 'arguments.resolution')
    if resolution is None:
        return
    split = resolution.lower().split('x')
    if len(split) < 2:
        return (Severity.ERROR,'resolution is not in correct format')
    res_width = split[0]
    res_height = split[1]
    if width is not None and width[2] != res_width:
        return (Severity.WARNING,'resolution width does not match video')
    if height is not None and height[2] != res_height:
        return (Severity.WARNING,'resolution height does not match video')

def checkFileTypeUnchanged(op, graph, frm, to):
    tofile =  graph.get_node(to)['file']
    fromfile = graph.get_node(frm)['file']
    if tofile.split('.')[-1].lower() != fromfile.split('.')[-1].lower():
        return (Severity.ERROR,
         "File type changed")
    return None

def checkAudioOutputType(op, graph, frm, to):
    tofile = os.path.join(graph.dir, graph.get_node(to)['file'])
    if fileType(tofile) != 'audio':
        return (Severity.ERROR,
         "Expecting Audio file type")
    return None

def _checkOutputType(graph,to,expected_types):
    newFileExtension = graph.get_image_path(to).split('.')[-1].lower()
    if newFileExtension not in expected_types:
        return (Severity.ERROR, "Output file extension " + newFileExtension.upper() + " doesn't match operation allowed extensions: " + ', '.join(expected_types))

def checkOutputType(op, graph, frm, to):
    extension = op.name.lower().split('put')[1]
    expected_extension = extension.lower()
    return _checkOutputType(graph,to,[expected_extension])

def checkOutputTypeM4(op, graph, frm, to):
    return _checkOutputType(graph, to, ['m4a','m4v'])

def checkJpgOutputType(op, graph, frm, to):
    return _checkOutputType(graph, to, ['jpg','jpeg'])

def checkTifOutputType(op, graph, frm, to):
    return _checkOutputType(graph, to, ['tif', 'tiff'])

def checkMp4OutputType(op, graph, frm, to):
    return _checkOutputType(graph, to, ['mp4', 'mpeg','mpg'])
    

def checkForAudio(op, graph, frm, to):
    """
         :param op:
         :param graph:
         :param frm:
         :param to:
         :return:
         @type op: Operation
         @type graph: ImageGraph
         @type frm: str
         @type to: str
    """
    def isSuccessor(graph, successors, node, ops):
        """
          :param scModel:
          :return:
          @type successors: list of str
          @type scModel: ImageProjectModel
          """
        for successor in successors:
            edge = graph.get_edge(node, successor)
            if edge['op'] not in ops:
                return False
        return True

    currentLink = graph.get_edge(frm, to)
    successors = graph.successors(to)
    if currentLink['op'] == 'AddAudioSample':
        sourceim, source = graph.get_image(frm)
        im, dest = graph.get_image(to)
        sourcemetadata = get_meta_from_video(source, show_streams=True, media_types=['audio'])[0]
        destmetadata = get_meta_from_video(dest, show_streams=True, media_types=['audio'])[0]
        if len(sourcemetadata) > 0:
            sourcevidcount = len([idx for idx, val in enumerate(sourcemetadata) if getValue(val,'codec_type','na') != 'audio'])
        if len(destmetadata) > 0:
            destvidcount = len(
                [x for x in (idx for idx, val in enumerate(destmetadata) if getValue(val,'codec_type','na') != 'audio')])
    if sourcevidcount != destvidcount:
        if not isSuccessor(graph, successors, to, ['AntiForensicCopyExif', 'OutputMP4', 'Donor']):
            return (Severity.ERROR,'Video is missing from audio sample')
    return None

def checkPasteFrameLength(op, graph, frm, to):
    """
         :param op:
         :param graph:
         :param frm:
         :param to:
         :return:
         @type op: Operation
         @type graph: ImageGraph
         @type frm: str
         @type to: str
    """
    edge = graph.get_edge(frm, to)
    addType = getValue(edge, 'arguments.add type')
    extractor = MetaDataExtractor(graph)
    to_masks = getMaskSetForEntireVideo(extractor.getMetaDataLocator(to),  media_types=['video'])
    frm_masks = getMaskSetForEntireVideo(extractor.getMetaDataLocator(frm), media_types=['video'])
    recordedMasks = extractor.getMasksFromEdge(frm, to, ['video'])
    recorded_change = sum([i['frames'] for i in recordedMasks if i['type'] == 'video'])
    diff = to_masks[0]['frames'] - frm_masks[0]['frames']

    if addType == 'replace' and diff > 0:
        return (Severity.ERROR,"Replacement contain not increase the size of video beyond the size of the donor")
    elif addType != 'replace' and diff != recorded_change:
        return (Severity.ERROR, "Pasted Frames did not equate to the amount of increased frames.  {} frames added".format(diff))


def checkLengthBigger(op, graph, frm, to):
    """
             :param op:
             :param graph:
             :param frm:
             :param to:
             :return:
             @type op: Operation
             @type graph: ImageGraph
             @type frm: str
             @type to: str
    """
    edge = graph.get_edge(frm, to)

    durationChangeTuple = getValue(edge, 'metadatadiff[0].video:nb_frames')
    if durationChangeTuple is None or \
            (durationChangeTuple[0] == 'change' and \
                         getMilliSecondsAndFrameCount(durationChangeTuple[1], defaultValue=(0,1))[0] >
                         getMilliSecondsAndFrameCount(durationChangeTuple[2], defaultValue=(0,1))[0]):
        return (Severity.ERROR,"Length of video is not longer")


def seamCarvingCheck(op, graph, frm, to):
    """
             :param op:
             :param graph:
             :param frm:
             :param to:
             :return:
             @type op: Operation
             @type graph: ImageGraph
             @type frm: str
             @type to: str
    """
    #change = getSizeChange(graph, frm, to)
    return None

def checkMoveMask(op, graph, frm,to):
    """
    Check move mask (input mask) is roughly the size and shape of the change mask.
    Overlap is considered, as the move might partially overlap the area from which the pixels
    came.
    :param op:
    :param graph:
    :param frm:
    :param to:
    :return:
    """
    edge = graph.get_edge(frm, to)
    try:
        maskname =getValue(edge,'maskname',defaultValue='')
        inputmaskname = getValue(edge,'inputmaskname',defaultValue='')
        if os.path.exists(os.path.join(graph.dir, inputmaskname)) and \
            os.path.exists(os.path.join(graph.dir, maskname)):
            mask = openImageFile(os.path.join(graph.dir, maskname)).invert().to_array()
            inputmask = openImage(os.path.join(graph.dir, inputmaskname)).to_mask().to_array()
            inputmask[inputmask > 0] = 1
            mask[mask > 0] = 1
            intersection = inputmask * mask
            leftover_mask = mask - intersection
            leftover_inputmask = inputmask - intersection
            masksize = np.sum(leftover_mask)
            inputmasksize = np.sum(leftover_inputmask)
            intersectionsize = np.sum(intersection)
            if inputmasksize == 0 and intersectionsize == 0:
                  return (Severity.ERROR,'input mask does not represent moved pixels. It is empty.')
            ratio_of_intersection = float(intersectionsize) / float(inputmasksize)
            ratio_of_difference = float(masksize) / float(inputmasksize)
            # intersection is too small or difference is too great
            if abs(ratio_of_difference - 1.0) > 0.25:
                  return (Severity.ERROR,'input mask does not represent the moved pixels')
    except Exception as ex:
        logging.getLogger('maskgen').error('Graph Validation Error checkMoveMask: ' + str(ex))
        return (Severity.ERROR,'Cannot validate Move Masks: ' + str(ex))

def checkHomography(op, graph, frm, to):
    edge = graph.get_edge(frm, to)
    tm = getValue(edge, 'arguments.transform matrix', getValue(edge, 'transform matrix'))
    if tm is not None:
        matrix = deserializeMatrix(tm)
        frm_shape = graph.get_image(frm)[0].size
        if not isHomographyOk(matrix, frm_shape[0], frm_shape[1]):
            return (Severity.ERROR, 'Homography appears to be erroneous.  Adjust Homography parameters.')
    return None

def fixPath(graph, start, end):
    preds = graph.predecessors(end)
    current_node, current_edge = [(pred,graph.get_edge(pred,end)) for pred in preds if pred != start][0]
    setPathValue(current_edge, 'transform matrix', None)
    im, path = graph.get_image(current_node)
    im.to_mask().invert().save(os.path.join(graph.dir,current_edge['maskname']))

def checkSIFT(op, graph, frm, to):
    """
    Currently a marker for SIFT.
    TODO: This operation should check SIFT transform matrix for images and video in the edge
    :param graph:
    :param frm:
    :param to:
    :return:
    """
    preds = graph.predecessors(to)
    for pred in preds:
        current_edge = graph.get_edge(pred,to)
        current_op = current_edge['op']
        result = checkHomography(op, graph, pred, to)
        if result is not None:
            if current_op == 'Donor':
                im, path = graph.get_image(pred)
                if im.has_alpha():
                    return (result[0],result[1],fixPath)
            return result


def sizeChanged(op, graph, frm, to):
    """
             :param op:
             :param graph:
             :param frm:
             :param to:
             :return:
             @type op: Operation
             @type graph: ImageGraph
             @type frm: str
             @type to: str
    """
    change = getSizeChange(graph, frm, to)
    if change is not None and (change[0] == 0 and change[1] == 0):
        return (Severity.ERROR,'operation should change the size of the image')
    return None

def checkSizeAndExifPNG(op, graph, frm, to):
    frm_shape = graph.get_image(frm)[0].size
    to_shape = graph.get_image(to)[0].size
    acceptable_change =(0.01 * frm_shape[0],0.01 * frm_shape[1])
    if frm_shape[0] == to_shape[0] and frm_shape[1] == to_shape[1]:
        return None
    if frm_shape[0] - to_shape[0] < acceptable_change[0] and frm_shape[1] - to_shape[1] < acceptable_change[1]:
        return (Severity.WARNING, 'operation is not permitted to change the size of the image')
    edge = graph.get_edge(frm, to)
    orientation = getValue(edge, 'exifdiff.Orientation')
    if orientation is None:
        orientation = getOrientationFromMetaData(edge)
    if orientation is not None:
        orientation = str(orientation)
        if ('270' in orientation or '90' in orientation):
            if frm_shape[0] - to_shape[1] == 0 and \
                                    frm_shape[1] - to_shape[0] == 0:
                return None
            if frm_shape[0] - to_shape[1] < acceptable_change[0] and \
                frm_shape[1] - to_shape[0] < acceptable_change[1]:
                return (Severity.WARNING, 'operation is not permitted to change the size of the image')
    return (Severity.ERROR, 'operation is not permitted to change the size of the image')

def checkSizeAndExif(op, graph, frm, to):
    """
             :param op:
             :param graph:
             :param frm:
             :param to:
             :return:
             @type op: Operation
             @type graph: ImageGraph
             @type frm: str
             @type to: str
    """
    change = getSizeChange(graph, frm, to)
    if change is not None and (change[0] != 0 or change[1] != 0):
        edge = graph.get_edge(frm, to)
        orientation = getValue(edge, 'exifdiff.Orientation')
        if orientation is None:
            orientation = getOrientationFromMetaData(edge)
        if orientation is not None:
            orientation = str(orientation)
            frm_img = graph.get_image(frm)[0]
            to_img = graph.get_image(to)[0]
            diff_frm = frm_img.size[0] - frm_img.size[1]
            diff_to = to_img.size[0] - to_img.size[1]
            if ('270' in orientation or '90' in orientation) and \
                numpy.sign(diff_frm) == numpy.sign(diff_to):
                return (Severity.ERROR, 'Rotation not applied')
            else:
                return None
        return (Severity.WARNING,'operation changed the size of the image')
    return None


def checkSize(op, graph, frm, to):
    """
             :param op:
             :param graph:
             :param frm:
             :param to:
             :return:
             @type op: Operation
             @type graph: ImageGraph
             @type frm: str
             @type to: str
    """
    change = getSizeChange(graph, frm, to)
    approach = getValue(graph.get_edge(frm, to), 'arguments.Approach', None)
    if approach == 'Crop':
        return None

    if change is not None and (change[0] != 0 or change[1] != 0):
        return (Severity.ERROR,'operation is not permitted to change the size of the image')
    return None


def _getSizeChange(edge):
    change = edge['shape change'] if edge is not None and 'shape change' in edge else None
    if change is not None:
        xyparts = change[1:-1].split(',')
        x = int(xyparts[0].strip())
        y = int(xyparts[1].strip())
        return (x, y)
    return None


def getSizeChange(graph, frm, to):
    return _getSizeChange(graph.get_edge(frm, to))


def getOrientationFromMetaData(edge):
    if 'metadatadiff' in edge:
        for item in edge['metadatadiff']:
            for k, v in item.iteritems():
                if k.find('rotate') > 0:
                    return v
    return None


def blurLocalRule(scModel, edgeTuples):
    found = False
    for edgeTuple in edgeTuples:
        if edgeTuple.edge['op'] == 'Blur':
            found = 'global' not in edgeTuple.edge or edgeTuple.edge['global'] == 'no'
        if found:
            break
    return 'yes' if found else 'no'


def histogramGlobalRule(scModel, edgeTuples):
    found = False
    for edgeTuple in edgeTuples:
        if edgeTuple.edge['op'] == 'Normalization':
            found = 'global' not in edgeTuple.edge or edgeTuple.edge['global'] == 'yes'
        if found:
            break
    return 'yes' if found else 'no'


def contrastGlobalRule(scModel, edgeTuples):
    found = False
    for edgeTuple in edgeTuples:
        if edgeTuple.edge['op'] == 'Contrast':
            found = 'global' not in edgeTuple.edge or edgeTuple.edge['global'] == 'yes'
        if found:
            break
    return 'yes' if found else 'no'


def colorGlobalRule(scModel, edgeTuples):
    """

    :param scModel:
    :param edgeTuples:
    :return:
    """
    found = False
    for edgeTuple in edgeTuples:
        op = scModel.getGroupOperationLoader().getOperationWithGroups(edgeTuple.edge['op'], fake=True)
        if op.category == 'Color' or (op.groupedCategories is not None and 'Color' in op.groupedCategories):
            found = True
            break
    return 'yes' if found else 'no'


def cloneRule(scModel, edgeTuples):
    for edgeTuple in edgeTuples:
        if ((edgeTuple.edge['op'] == 'PasteSplice' and scModel.getGraph().predecessorsHaveCommonParent(edgeTuple.end)) or \
                    (edgeTuple.edge['op'] == 'PasteSampled' and \
                                 edgeTuple.edge['arguments']['purpose'] == 'clone')):
            return 'yes'
    return 'no'


def unitCountRule(scModel, edgeTuples):
    setofops = set(['SelectRegion','SelectRegionFromFrames','SelectImageFromFrame','AudioSample'])
    count = 0
    for edgeTuple in edgeTuples:
        op = scModel.getGroupOperationLoader().getOperationWithGroups(edgeTuple.edge['op'], fake=True)
        count += 1 if op.category not in ['Output',  'Donor'] and edgeTuple.edge['op'] not in setofops else 0
        setofops.add(edgeTuple.edge['op'])
    return str(count) + '-Unit'


def voiceOverlay(scModel, edgeTuples):
    for edgeTuple in edgeTuples:
        if 'arguments' in edgeTuple.edge and \
                        'voice' in edgeTuple.edge['arguments'] and \
                        edgeTuple.edge['arguments']['voice'] == 'yes' and \
                        'add type' in edgeTuple.edge['arguments'] and \
                        edgeTuple.edge['arguments']['add type'] == 'overlay':
            return 'yes'
    return 'no'


def spatialClone(scModel, edgeTuples):
    for edgeTuple in edgeTuples:
        if scModel.getNodeFileType(edgeTuple.start) != 'video':
            continue
        if edgeTuple.edge['op'] == 'PasteOverlay' and \
                scModel.getGraph().predecessorsHaveCommonParent(edgeTuple.end) and \
                ('arguments' not in edgeTuple.edge or \
                         ('purpose' in edgeTuple.edge['arguments'] and \
                                      edgeTuple.edge['arguments']['purpose'] == 'add')):
            return 'yes'
        if edgeTuple.edge['op'] == 'PasteSampled' and \
                        'arguments' in edgeTuple.edge and \
                        'purpose' in edgeTuple.edge['arguments'] and \
                        edgeTuple.edge['arguments']['purpose'] == 'clone':
            return 'yes'
    return 'no'


def spatialSplice(scModel, edgeTuples):
    for edgeTuple in edgeTuples:
        if scModel.getNodeFileType(edgeTuple.start) != 'video':
            continue
        if edgeTuple.edge['op'] == 'PasteOverlay' and \
                not scModel.getGraph().predecessorsHaveCommonParent(edgeTuple.end) and \
                ('arguments' not in edgeTuple.edge or \
                         ('purpose' in edgeTuple.edge['arguments'] and \
                                      edgeTuple.edge['arguments']['purpose'] == 'add')):
            return 'yes'
        if edgeTuple.edge['op'] == 'PasteImageSpliceToFrame' and \
            getValue(edgeTuple.edge, 'arguments.purpose') == 'clone':
            return 'yes'
    return 'no'


def spatialRemove(scModel, edgeTuples):
    for edgeTuple in edgeTuples:
        if scModel.getNodeFileType(edgeTuple.start) != 'video':
            continue
        if edgeTuple.edge['op'] in ['PasteSampled', 'PasteOverlay', 'PasteImageSpliceToFrame'] and \
                        getValue(edgeTuple.edge,'arguments.purpose') == 'remove':
            return 'yes'
    return 'no'


def spatialMovingObject(scModel, edgeTuples):
    for edgeTuple in edgeTuples:
        if scModel.getNodeFileType(edgeTuple.start) != 'video':
            continue
        if edgeTuple.edge['op'] in ['PasteSampled', 'PasteOverlay', 'PasteImageSpliceToFrame'] and \
                        getValue(edgeTuple.edge, 'arguments.motion mapping') == 'yes':
            return 'yes'
    return 'no'


def voiceSwap(scModel, edgeTuples):
    for edgeTuple in edgeTuples:
        if getValue(edgeTuple.edge, 'arguments.voice') =='yes' and \
             getValue(edgeTuple.edge, 'arguments.add type') == 'replace':
            return 'yes'
    return 'no'


def imageReformatRule(scModel, edgeTuples):
    """
       :param scModel:
       :param edgeTuples:
       :return:
       @type scModel: ImageProjectModel
       """
    start = end = None
    for edgeTuple in edgeTuples:
        if len(scModel.getGraph().predecessors(edgeTuple.start)) == 0:
            start = edgeTuple.start
        elif len(scModel.getGraph().successors(edgeTuple.end)) == 0:
            end = edgeTuple.end
    if end and start:
        snode = scModel.getGraph().get_node(start)
        enode = scModel.getGraph().get_node(end)
        startexif = exif.getexif(os.path.join(scModel.get_dir(), snode['file']))
        endexif = exif.getexif(os.path.join(scModel.get_dir(), enode['file']))
        if 'MIME Type' in startexif and 'MIME Type' in endexif and \
                        startexif['MIME Type'] != endexif['MIME Type']:
            return 'yes'
        elif 'File Type' in startexif and 'File Type' in endexif and \
                        startexif['File Type'] != endexif['File Type']:
            return 'yes'
    return 'no'


def medianSmoothingRule(scModel, edgeTuples):
    for edgeTuple in edgeTuples:
        if edgeTuple.edge['op'] == 'Blur' and \
                        'arguments' in edgeTuple.edge and \
                        'Blur Type' in edgeTuple.edge['arguments'] and \
                        edgeTuple.edge['arguments']['Blur Type'] == 'Median Smoothing':
            return 'yes'
    return 'no'


def imageCompressionRule(scModel, edgeTuples):
    """

    :param scModel:
    :param edgeTuples:
    :return:
    @type scModel: ImageProjectModel
    """
    for edgeTuple in edgeTuples:
        if len(scModel.getGraph().successors(edgeTuple.end)) == 0:
            node = scModel.getGraph().get_node(edgeTuple.end)
            result = exif.getexif(os.path.join(scModel.get_dir(), node['file']))
            compression = result['Compression'].strip() if 'Compression' in result else None
            jpeg = result['File Type'].lower() == 'jpeg' if 'File Type' in result else False
            return 'yes' if jpeg or (
            compression and len(compression) > 0 and not compression.lower().startswith('uncompressed')) else 'no'
    return 'no'


def semanticEventFabricationRule(scModel, edgeTuples):
    return scModel.getProjectData('semanticrefabrication')


def semanticRepurposeRule(scModel, edgeTuples):
    return scModel.getProjectData('semanticrepurposing')


def semanticRestageRule(scModel, edgeTuples):
    return scModel.getProjectData('semanticrestaging')


def audioactivityRule(scModel, edgeTuples):
    for edgeTuple in edgeTuples:
        op = scModel.getGroupOperationLoader().getOperationWithGroups(edgeTuple.edge['op'], fake=True)
        found = (op.category == 'Audio')
        if not found and op.groupedOperations is not None:
            for imbedded_op_name in op.groupedOperations:
                imbedded_op = scModel.getGroupOperationLoader().getOperationWithGroups(imbedded_op_name,fake=True)
                found |= imbedded_op.category == 'Audio'
    return 'yes' if found else 'no'


def compositeSizeRule(scModel, edgeTuples):
    value = 0
    composite_rank = ['small', 'medium', 'large']
    for edgeTuple in edgeTuples:
        if 'change size category' in edgeTuple.edge and 'recordMaskInComposite' in edgeTuple.edge and \
                        edgeTuple.edge['recordMaskInComposite'] == 'yes':
            value = max(composite_rank.index(edgeTuple.edge['change size category']), value)
    return composite_rank[value]


def _checkOpOther(op):
    if op.category in ['AdditionalEffect', 'Fill', 'Transform', 'Intensity', 'Layer', 'Filter', 'CGI']:
        if op.name not in ['Blur', 'Sharpening', 'TransformResize',
                           'TransformCrop', 'TransformRotate', 'TransformSeamCarving',
                           'TransformWarp', 'Normalization', 'Contrast']:
            return True
    return False


def provenanceRule(scModel, edgeTuples):
    """
    :param scModel:
    :param edgeTuples:
    :return:
    @type scModel: ImageProjectModel
    """
    bases = set()
    for node in scModel.getNodeNames():
        nodedata = scModel.getGraph().get_node(node)
        if nodedata['nodetype'] == 'final':
            bases.add(scModel.getBaseNode(node))
    return 'yes' if len(bases) > 1 else 'no'


def manipulationCategoryRule(scModel, edgeTuples):
    best = ''
    for node in scModel.getNodeNames():
        nodedata = scModel.getGraph().get_node(node)
        if 'pathanalysis' in nodedata and \
                        'manipulationcategory' in nodedata['pathanalysis'] and \
                        nodedata['pathanalysis']['manipulationcategory'] > best:
            best = nodedata['pathanalysis']['manipulationcategory']
    return best

def otherEnhancementRule(scModel, edgeTuples):
    found = False
    for edgeTuple in edgeTuples:
        if scModel.getNodeFileType(edgeTuple.start) != 'image':
            continue
        op = scModel.getGroupOperationLoader().getOperationWithGroups(edgeTuple.edge['op'], fake=True)
        found = _checkOpOther(op)
        if not found and op.groupedOperations is not None:
            for imbedded_op in op.groupedOperations:
                found |= _checkOpOther(scModel.getGroupOperationLoader().getOperationWithGroups(imbedded_op, fake=True))
        if found:
            break
    return 'yes' if found else 'no'


def videoOtherEnhancementRule(scModel, edgeTuples):
    found = False
    for edgeTuple in edgeTuples:
        if scModel.getNodeFileType(edgeTuple.start) != 'video':
            continue
        op = scModel.getGroupOperationLoader().getOperationWithGroups(edgeTuple.edge['op'], fake=True)
        found = _checkOpOther(op)
        if not found and op.groupedOperations is not None:
            for imbedded_op in op.groupedOperations:
                found |= _checkOpOther(scModel.getGroupOperationLoader().getOperationWithGroups(imbedded_op, fake=True))
        if found:
            break
    return 'yes' if found else 'no'


def _filterEdgesByOperatioName(edges, opName):
    return [edgeTuple for edgeTuple in edges if edgeTuple.edge['op'] == opName]


def _filterEdgesByNodeType(scModel, edges, nodetype):
    return [edgeTuple for edgeTuple in edges if scModel.getNodeFileType(edgeTuple.start) == nodetype]


def ganComponentRule(scModel, edges):
    for edgeTuple in edges:
        if edgeTuple.edge['op'] == 'ObjectCGI' and \
            getValue(edgeTuple.edge,'arguments.isGAN','no') == 'yes':
            return 'yes'
        elif edgeTuple.edge['op'] == 'PasteSplice' and \
                'gan' in getValue(edgeTuple.edge, 'arguments.subject', 'no'):
            return 'yes'

    return 'no'

def _cleanEdges(scModel, edges):
    for edgeTuple in edges:
        node = scModel.getGraph().get_node(edgeTuple.end)
        if "pathanalysis" in node:
            node.pop("pathanalysis")
    return [edgeTuple for edgeTuple in edges]


def setFinalNodeProperties(scModel, finalNode):
    """

    :param scModel: ImageProjectModel
    :param finalNode:
    :return:
    @type: ImageProjectModel
    @rtype: dict
    """
    _setupPropertyRules()
    edges = _cleanEdges(scModel, scModel.getEdges(finalNode))
    edgesAll = scModel.getEdges(finalNode,excludeDonor=False)
    analysis = dict()
    for prop in getProjectProperties():
        if not prop.node and not prop.semanticgroup:
            continue
        filtered_edges = edgesAll if prop.includedonors else edges
        if prop.nodetype is not None:
            filtered_edges = _filterEdgesByNodeType(scModel, filtered_edges, prop.nodetype)
        if prop.semanticgroup:
            foundOne = False
            for edgeTuple in filtered_edges:
                if 'semanticGroups' in edgeTuple.edge and edgeTuple.edge['semanticGroups'] is not None and \
                                prop.description in edgeTuple.edge['semanticGroups']:
                    foundOne = True
                    break
            analysis[prop.name] = 'yes' if foundOne else 'no'
        if prop.operations is not None and len(prop.operations) > 0:
            foundOne = False
            for op in prop.operations:
                filtered_edges = _filterEdgesByOperatioName(filtered_edges, op)
                foundOne |= ((prop.parameter is None and len(filtered_edges) > 0) or len(
                    [edgeTuple for edgeTuple in filtered_edges
                     if 'arguments' in edgeTuple.edge and \
                     prop.parameter in edgeTuple.edge['arguments'] and \
                     edgeTuple.edge['arguments'][prop.parameter] == prop.value]) > 0)
            analysis[prop.name] = 'yes' if foundOne else 'no'
        if prop.rule is not None and getValue(analysis, prop.name,'no') == 'no':
            analysis[prop.name] = project_property_rules[propertyRuleIndexKey(prop)](scModel, edges)
    scModel.getGraph().update_node(finalNode, pathanalysis=analysis)
    return analysis


def processProjectProperties(scModel, rule=None):
    """
    Update the model's project properties inspecting the rules associated with project properties
    :param scModel: ScenarioModel
    :return:
    """
    _setupPropertyRules()
    for prop in getProjectProperties():
        edges = None
        if (rule is not None and (prop.rule is None or prop.rule != rule)) or prop.node:
            continue
        if prop.operations is not None and len(prop.operations) > 0:
            foundOne = False
            for op in prop.operations:
                edges = scModel.findEdgesByOperationName(op)
                foundOne |= (prop.parameter is None or len([edge for edge in edges if 'arguments' in edge and \
                                                            edge['arguments'][prop.parameter] == prop.value]) > 0)
            scModel.setProjectData(prop.name, 'yes' if foundOne else 'no')
        if prop.rule is not None:
            scModel.setProjectData(prop.name, project_property_rules[propertyRuleIndexKey(prop)](scModel, edges))


def propertyRuleIndexKey(prop):
    """
    Since node and project properties can have the same name, a index into the single rule function list
    must differentiate.
    :param prop:
    :return:
    @type prop : ProjectProperty
    @rtype string
    """
    return ('n' if prop.node else 'p') + prop.name


def _setupPropertyRules():
    global project_property_rules
    if len(project_property_rules) == 0:
        for prop in getProjectProperties():
            if prop.rule is not None:
                project_property_rules[propertyRuleIndexKey(prop)] = getRule(prop.rule, globals=globals())


def getNodeSummary(scModel, node_id):
    """
    Return path analysis.  This only applicable after running processProjectProperties()
    :param scModel:
    :param node_id:
    :return:  None if not found
    @type scModel: ImageProjectModel
    @type node_id: str
    @rtype: dict
    """
    node = scModel.getGraph().get_node(node_id)
    return node['pathanalysis'] if node is not None and 'pathanalysis' in node else None





