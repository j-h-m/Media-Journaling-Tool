import cv2
import numpy as np
import math
from datetime import datetime
from skimage.measure import compare_ssim
import warnings
from scipy import ndimage
from scipy import misc
import getpass
import re
import imghdr
import h5py
import os
from image_wrap import *

imagefiletypes = [("jpeg files", "*.jpg"), ("png files", "*.png"), ("tiff files", "*.tiff"), ("Raw NEF", ".nef"),
                  ("bmp files", "*.bmp"), ("avi files", "*.avi")]

videofiletypes = [("mpeg files", "*.mp4"), ("mov files", "*.mov"), ('wmv', '*.wmv'), ('m4p', '*.m4p'), ('m4v', '*.m4v'),
                  ('f4v', '*.flv')]

suffixes = ["*.nef", ".jpg", ".png", ".tiff", "*.bmp", ".avi", ".mp4", ".mov", "*.wmv", "*.ppm", "*.pbm", "*.gif"]
maskfiletypes = [("png files", "*.png"), ("zipped masks", "*.tgz"), ("mpeg files", "*.mp4")]


def getMaskFileTypes():
    return maskfiletypes


def getFileTypes():
    return imagefiletypes + videofiletypes


def fileTypeChanged(file_one, file_two):
    """
     Return: True if the file types of the two provided files do not match
    """
    try:
        one_type = imghdr.what(file_one)
        two_type = imghdr.what(file_two)
        return one_type != two_type
    except:
        pos = file_one.rfind('.')
        suffix_one = file_one[pos + 1:] if pos > 0 else ''
        pos = file_two.rfind('.')
        suffix_two = file_two[pos + 1:] if pos > 0 else ''
        return suffix_one.lower() != suffix_two.lower()

def fileType(fileName):
    pos = fileName.rfind('.')
    suffix = fileName[pos + 1:] if pos > 0 else ''
    return 'image' if (suffix in imagefiletypes or imghdr.what(fileName) is not None) else 'video'


def openFile(fileName):
    """
     Open a file using a native OS associated program
    """
    import os
    import sys
    if fileName.endswith('.hdf5'):
        fileName = convertToMP4(fileName)
    if sys.platform.startswith('linux'):
        os.system('xdg-open "' + fileName + '"')
    elif sys.platform.startswith('win'):
        os.startfile(fileName)
    else:
        os.system('open "' + fileName + '"')


"""
   Support UID discovery using a class that supports a method getpwuid().
   tool_set.setPwdX(classInstance) to set the class.  By default, the os UID is used.
"""

try:
    import pwd
    import os


    class PwdX():
        def getpwuid(self):
            return pwd.getpwuid(os.getuid())[0]

except ImportError:
    class PwdX():
        def getpwuid(self):
            return getpass.getuser()

pwdAPI = PwdX()


class CustomPwdX:
    uid = None

    def __init__(self, uid):
        self.uid = uid

    def getpwuid(self):
        return self.uid


def setPwdX(api):
    global pwdAPI
    pwdAPI = api


def get_username():
    return pwdAPI.getpwuid()

def imageResize(img, dim):
    return img.resize(dim,Image.ANTIALIAS).convert('RGBA')

def imageResizeRelative(img, dim, otherIm):
    wmax = max(img.size[0], otherIm[0])
    hmax = max(img.size[1], otherIm[1])
    wpercent = float(dim[0]) / float(wmax)
    hpercent = float(dim[1]) / float(hmax)
    perc = min(wpercent, hpercent)
    wsize = int((float(img.size[0]) * float(perc)))
    hsize = int((float(img.size[1]) * float(perc)))
    return img.resize((wsize, hsize),Image.ANTIALIAS)


def validateCoordinates(v):
    """
    Coordinates are [x,y] or (x,y) or x,y where x and y are integers.
    Return False if the coordinates are invalid.
    """
    try:
        return len([int(re.sub('[()]', '', x)) for x in v.split(',')]) == 2
    except ValueError:
        return False

def isPastTime(milliAndFrameNow, milliAndFrameMark):
    """
    :param milliAndFrameNow:  tuple (milliseconds, frames since time)
    :param milliAndFrameMark: tuple (milliseconds, frames since time)
    :return: True if milliAndFrameNow > milliAndFrameMark
    """
    if milliAndFrameMark is None or milliAndFrameMark[0] is None:
        return False
    if milliAndFrameNow[0] > milliAndFrameMark[0]:
        return True
    if milliAndFrameNow[0] == milliAndFrameMark[0]:
        return milliAndFrameMark[1] is not None and milliAndFrameNow[1] > milliAndFrameMark[1]
    return False

def isBeforeTime(milliAndFrameNow, milliAndFrameMark):
    """
    :param milliAndFrameNow:  tuple (milliseconds, frames since time)
    :param milliAndFrameMark: tuple (milliseconds, frames since time)
    :return: True if milliAndFrameNow > milliAndFrameMark
    """
    if milliAndFrameMark is None or milliAndFrameMark[0] is None:
        return False
    if milliAndFrameNow[0] < milliAndFrameMark[0]:
        return True
    if milliAndFrameNow[0] == milliAndFrameMark[0]:
        return milliAndFrameMark[1] is not None and milliAndFrameNow[1] < milliAndFrameMark[1]
    return False


def getMilliSeconds(v):
    dt = None
    framecount = 0
    if v.count(':') > 2:
        try:
            framecount = int(v[v.rfind(':') + 1:])
            v = v[0:v.rfind(':')]
        except:
            return None,0
    try:
        dt =  datetime.strptime(v, '%H:%M:%S.%f')
    except ValueError:
        try:
            dt =  datetime.strptime(v, '%H:%M:%S')
        except ValueError:
            return None,0
    return (dt.hour*360000 + dt.minute*60000 + dt.second*1000 + dt.microsecond/1000,framecount)

def validateTimeString(v):
    if v.count(':') > 3:
       return False

    framecount = 0
    if v.count(':') > 2:
        try:
             framecount = int(v[v.rfind(':')+1:])
             v = v[0:v.rfind(':')]
        except:
             return False
    try:
        datetime.strptime(v, '%H:%M:%S.%f')
    except ValueError:
        try:
            datetime.strptime(v, '%H:%M:%S')
        except ValueError:
            return False
    return True


def validateAndConvertTypedValue(argName, argValue, operationDef):
    """
      Validate a typed operation argument
      return the type converted argument if necessary
      raise a ValueError if invalid
    """
    if not argValue or len(str(argValue)) == 0:
        raise ValueError(argName + ' cannot be an empty string')
    argDef = operationDef.optionalparameters[argName] if argName in operationDef.optionalparameters else None
    argDef = operationDef.mandatoryparameters[
        argName] if not argDef and argName in operationDef.mandatoryparameters else argDef
    if argDef:
        if argDef['type'].startswith('float'):
            typeDef = argDef['type']
            vals = [float(x) for x in typeDef[typeDef.rfind('[') + 1:-1].split(':')]
            if float(argValue) < vals[0] or float(argValue) > vals[1]:
                raise ValueError(argName + ' is not within the defined range')
            return float(argValue)
        elif argDef['type'].startswith('int'):
            typeDef = argDef['type']
            vals = [int(x) for x in typeDef[typeDef.rfind('[') + 1:-1].split(':')]
            if int(argValue) < vals[0] or int(argValue) > vals[1]:
                raise ValueError(argName + ' is not within the defined range')
            return int(argValue)
        elif argDef['type'] == 'list':
            if argValue not in argDef['values']:
                raise ValueError(argName + ' is not one of the allowed values')
        elif argDef['type'] == 'time':
            if not validateTimeString(argValue):
                raise ValueError(argName + ' is not a valid time (e.g. HH:MM:SS.micro)')
        elif argDef['type'] == 'yesno':
            if argValue.lower() not in ['yes', 'no']:
                raise ValueError(argName + ' is not yes or no')
        elif argDef['type'] == 'coorindates':
            if not validateCoordinates(argValue):
                raise ValueError(argName + ' is not a valid coordinate (e.g. (6,4)')
    return argValue


def openImage(filename, videoFrameTime=None, isMask=False, preserveSnapshot=False):
    """
    Open and return an image from the file. If the file is a video, find the first non-uniform frame.
    videoFrameTime, integer time in milliseconds, is provided, then find the frame after that point in time
    preserveSnapshot, False by default, informs the function to save the frame image after extraction for videos
    """
    import os
    from scipy import ndimage

    snapshotFileName = filename
    if not os.path.exists(filename):
        return openImage('./icons/RedX.png')

    if filename[filename.rfind('.') + 1:].lower() in ['avi', 'mp4', 'mov', 'flv', 'qt', 'wmv', 'm4p', 'mpeg', 'mpv',
                                                      'm4v']:
        snapshotFileName = filename[0:filename.rfind('.') - len(filename)] + '.png'

    if videoFrameTime is not None or \
        (snapshotFileName != filename and \
         (not os.path.exists(snapshotFileName) or \
            os.stat(snapshotFileName).st_mtime < os.stat(filename).st_mtime)):
        cap = cv2.VideoCapture(filename)
        bestSoFar = None
        bestVariance = -1
        maxTry = 20
        secondInMillis = 0
        framesSinceSecond = 0
        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                currentSecond = int(float(cap.get(cv2.cv.CV_CAP_PROP_POS_MSEC))/1000.0)*1000
                if currentSecond > secondInMillis:
                    secondInMillis = currentSecond
                    framesSinceSecond = 1
                else:
                    framesSinceSecond+=1
                if isPastTime((currentSecond,framesSinceSecond),videoFrameTime):
                    bestSoFar = frame
                    break
                varianceOfImage = math.sqrt(ndimage.measurements.variance(frame))
                if frame is not None and bestVariance < varianceOfImage:
                    bestSoFar = frame
                    bestVariance = varianceOfImage
                maxTry -= 1
                if not videoFrameTime and maxTry <= 0:
                    break
        finally:
            cap.release()
        if bestSoFar is None:
            print 'invalid or corrupted file ' + filename
            return openImage('./icons/RedX.png')
        img = ImageWrapper(bestSoFar, to_mask=isMask)
        if preserveSnapshot and snapshotFileName != filename:
            img.save(snapshotFileName)
        return img
    else:
        try:
            img = openImageFile(snapshotFileName)
            return img
        except IOError as e:
            print e
            return openImage('./icons/RedX.png')


def interpolateMask(mask, img1, img2, invert=False, arguments=dict()):
    maskInverted = mask if invert else mask.invert()
    mask = np.asarray(mask)
    TM, computed_mask = __sift(img1, img2, mask2=maskInverted)
    if TM is not None:
        newMask = cv2.warpPerspective(mask, TM, (img1.size[0],img1.size[1]), flags=cv2.WARP_INVERSE_MAP,borderMode=cv2.BORDER_CONSTANT, borderValue=255)
        analysis = {}
        analysis['transform matrix'] = serializeMatrix(TM)
        return newMask if computed_mask is None else computed_mask, analysis
    else:
        try:
            contours, hier = cv2.findContours(255 - mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            minpoint = None
            maxpoint = None
            for contour in contours:
                for point in contour:
                    if type(point[0]) is np.ndarray:
                        point = point[0]
                    if minpoint is None:
                        minpoint = point
                    else:
                        minpoint = (min(minpoint[0], point[0]), min(minpoint[1], point[1]))
                    if maxpoint is None:
                        maxpoint = point
                    else:
                        maxpoint = (max(maxpoint[0], point[0]), max(maxpoint[1], point[1]))
            w = maxpoint[0] - minpoint[0] + 1
            h = maxpoint[1] - minpoint[1] + 1
            x = minpoint[0]
            y = minpoint[1]
            if (img1.size[0] - w) < 2 and (img1.size[1] - h) < 2:
                return mask[x:x + h, y:y + w], {}
        except:
            return None, None
        return None, None


def serializeMatrix(m):
    data = {}
    data['r'] = m.shape[0]
    data['c'] = m.shape[1]
    for r in range(m.shape[0]):
        data['r' + str(r)] = list(m[r, :])
    return data


def deserializeMatrix(data):
    m = np.zeros((int(data['r']), int(data['c'])))
    for r in range(m.shape[0]):
        m[r, :] = data['r' + str(r)]
    return m


def redistribute_intensity(edge_map):
    """
    Produce a intensity_map that redistributes the intensity values found in the edge_map evenly over 1 to 255
    :param edge_map contains a map between an edge identifier (s,e) and an intensity value from 1 to 255
    :return map of intensity value from edge map to a replacement intensity value
    """
    intensities = sorted(edge_map.values())
    intensity_map = {}
    increment = int(255 / (len(intensities) + 1))
    pos = 1
    for i in intensities:
        intensity_map[i] = pos * increment
        pos += 1
    return intensity_map


def toColor(img, edge_map={}, intensity_map={}):
    """
    Produce an image that changes gray scale to color.
    First, set the intensity values of each pixel using the intensity value from the intensity map
    Then use a color map to build a color image
    Then repopulate the edge_map with the assigned color for each edge
    :param img gray scale image
    :param edge_map edge identifier associated with an intensity value (0 to 254)
    :param intensity_map intensity value mapped to its replacement
    :return the new color image
    """
    for old, new in intensity_map.iteritems():
        img[img == old] = new
    result = cv2.applyColorMap(img.astype('uint8'), cv2.COLORMAP_HSV)
    result[img == 255] = [255, 255, 255]
    for k, v in edge_map.iteritems():
        coords = np.where(img == intensity_map[v]) if v in intensity_map  else None
        if coords is not None and len(coords[0]) > 0:
            edge_map[k] = result[coords[0][0], coords[1][0], :]
    return result

def globalTransformAnalysis(analysis,img1,img2,mask=None,arguments={}):
    globalchange = img1.size != img2.size
    totalPossible = reduce(lambda a,x: a*x,img1.size)
    totalChange = totalPossible
    ratio = 1.0
    if mask is not None:
      mask = np.asarray(mask)
      totalChange = sum(sum(mask.astype('float32')))/255.0
      ratio = float(totalChange)/float(totalPossible)
      if not globalchange:
        globalchange = ratio > 0.75
        kernel = np.ones((5,5),np.uint8)
        erosion = cv2.erode(mask,kernel,iterations = 2)
        closing = cv2.morphologyEx(erosion, cv2.MORPH_CLOSE, kernel)
        contours, hierarchy = cv2.findContours(closing,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        p = np.asarray([item[0] for sublist in contours for item in sublist])
        if len(p) > 0:
           area = cv2.contourArea(cv2.convexHull(p))
           totalArea = cv2.contourArea(np.asarray([[0,0],[0,mask.shape[0]],[mask.shape[1],mask.shape[0]], [mask.shape[1],0],[0,0]]))
           globalchange = globalchange or area/totalArea > 0.50
    analysis['global'] = 'yes' if globalchange else 'no'
    analysis['change size ratio'] = ratio
    analysis['change size category'] = 'small' if totalChange<2500 else ('medium' if totalChange<10000 else 'large')
    return globalchange


def siftAnalysis(analysis, img1, img2, mask=None, arguments=dict()):
    if globalTransformAnalysis(analysis, img1, img2, mask=mask, arguments=arguments):
        return
    mask2 = mask.resize(img2.size) if mask is not None and img1.size != img2.size else mask
    matrix,mask = __sift(img1, img2, mask1=mask, mask2=mask2)
    if matrix is not None:
        analysis['transform matrix'] = serializeMatrix(matrix)


def createMask(img1, img2, invert=False, arguments={}):
    mask, analysis = __composeMask(img1, img2, invert, arguments=arguments)
    analysis['shape change'] = __sizeDiff(img1, img2)
    return ImageWrapper(mask), analysis


def __indexOf(source, dest):
    positions = []
    for spos in range(len(source)):
        for dpos in range(len(dest)):
            if (source[spos] == dest[dpos]).all():
                positions.append(spos)
                break
    return positions

def __sift(img1, img2, mask1=None, mask2=None):
    img1 = img1.to_rgb().apply_mask(mask1).to_array()
    img2 = img2.to_rgb().apply_mask(mask2).to_array()

    detector = cv2.FeatureDetector_create("SIFT")
    extractor = cv2.DescriptorExtractor_create("SIFT")


    FLANN_INDEX_KDTREE = 0
    FLANN_INDEX_LSH = 6
    TREES=16
    index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=TREES)
    # index_params= dict(algorithm         = FLANN_INDEX_LSH,
    #                   table_number      = 6,
    #                   key_size          = 12,
    #                   multi_probe_level = 1)
    search_params = dict(checks=50)

    flann = cv2.FlannBasedMatcher(index_params, search_params)

    kp1a = detector.detect(img1)
    kp2a = detector.detect(img2)

    (kp1, d1) = extractor.compute(img1, kp1a)
    (kp2, d2) = extractor.compute(img2, kp2a)

    if kp2 is None or len(kp2) == 0:
        return None,None

    if kp1 is None or len(kp1) == 0:
        return None,None

    d1 /= (d1.sum(axis=1, keepdims=True) + 1e-7)
    d1 = np.sqrt(d1)

    d2 /= (d2.sum(axis=1, keepdims=True) + 1e-7)
    d2 = np.sqrt(d2)

    matches = flann.knnMatch(d1, d2, k=2) if d1 is not None and d2 is not None else []

    # store all the good matches as per Lowe's ratio test.
    good = [m for m, n in matches if m.distance < 0.8 * n.distance]

    if len(good) >= 10:
        src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        #new_src_pts = cv2.convexHull(src_pts)
        new_src_pts = src_pts
        #positions = __indexOf(src_pts,new_src_pts)
        #new_dst_pts = dst_pts[positions]
        new_dst_pts = dst_pts

        M, mask = cv2.findHomography(new_src_pts, new_dst_pts, cv2.RANSAC, 3.0)
        #M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        #matchesMask = mask.ravel().tolist()

        #y,x = img1.shape
        #pts = np.float32([ [0,0],[0,y-1],[x-1,y-1],[x-1,0] ]).reshape(-1,1,2)
        #dst = cv2.perspectiveTransform(pts,M)
        #mask = np.zeros((img1.shape[0],img1.shape[1]))
        #new_src_pts1 = [point[0] for point in new_src_pts.astype('int32')]
        #new_src_pts1 = [__calc_alpha2(0.3,new_src_pts1)]
        #cv2.fillPoly(mask, np.int32([new_src_pts1]), 255)
        ##img1 = cv2.polylines(img1, [np.int32(dst)], True, 255, 3, cv2.LINE_AA)
        return M,None#mask.astype('uint8')

        # img2 = cv2.polylines(img2,[np.int32(dst)],True,255,3, cv2.LINE_AA)
    # Sort them in the order of their distance.
    return None,None


def __applyTransform(compositeMask, mask, transform_matrix,invert=False):
    maskInverted = ImageWrapper(np.asarray(mask)).invert().to_array()
    maskInverted[maskInverted > 0] = 1
    compositeMaskFlipped = 255 - compositeMask
    compositeMaskAltered = compositeMaskFlipped * maskInverted
    flags=cv2.WARP_INVERSE_MAP if invert else cv2.INTER_LINEAR#+cv2.CV_WARP_FILL_OUTLIERS
    newMask = cv2.warpPerspective(compositeMaskAltered, transform_matrix, (mask.shape[1], mask.shape[0]), flags=flags)
    maskAltered  = np.copy(mask)
    maskAltered[maskAltered > 0] = 1
    compositeMaskAltered = compositeMaskFlipped * maskAltered
    newMask[compositeMaskAltered > 0] = 255
    return 255 - newMask

def __composeMask(img1, img2, invert, arguments=dict()):
    img1, img2 = __alignChannels(img1, img2, equalize_colors='equalize_colors' in arguments)
    # rotate image two if possible to compare back to image one.
    # The mask is not perfect.
    rotation = float(arguments['rotation']) if 'rotation' in arguments else 0.0
    if abs(rotation) > 0.0001 and img1.shape != img2.shape:
        return __compareRotatedImage(rotation, img1, img2, invert, arguments)
    if (sum(img1.shape) > sum(img2.shape)):
        return __composeCropImageMask(img1, img2)
    if (sum(img1.shape) < sum(img2.shape)):
        return __composeExpandImageMask(img1, img2)
    try:
        if img1.shape == img2.shape:
            return __diffMask(img1, img2, invert,args=arguments)
    except ValueError as e:
        print 'Mask generation failure ' + str(e)
    mask = np.ones(img1.shape) * 255
    return abs(255 - mask).astype('uint8'), {}


def __alignShape(im, shape):
    x = min(shape[0], im.shape[0])
    y = min(shape[1], im.shape[1])
    z = np.zeros(shape)
    for d in range(min(shape[2], im.shape[2])):
        z[0:x, 0:y, d] = im[0:x, 0:y, d]
    return z


def __resize(img, dimensions):
    if img.shape[0] != dimensions[0]:
        diff = abs(img.shape[0] - dimensions[0])
        img = np.concatenate((np.zeros((diff / 2, img.shape[1])), img), axis=0)
        img = np.concatenate((img, np.zeros((diff - (diff / 2), img.shape[1]))), axis=0)
    if img.shape[1] != dimensions[1]:
        diff = abs(img.shape[1] - dimensions[1])
        img = np.concatenate((np.zeros((img.shape[0], diff / 2)), img), axis=1)
        img = np.concatenate((img, np.zeros((img.shape[0], diff - (diff / 2)))), axis=1)
    return img


def __rotateImage(rotation, img, expectedDims, cval=0):
    #   (h, w) = image.shape[:2]
    #   center = (w / 2, h / 2) if rotationPoint=='center' else (0,0)
    #   M = cv2.getRotationMatrix2D(center, rotation, 1.0)
    #   rotated = cv2.warpAffine(image, M, (w, h))
    rotNorm = int(rotation / 90) if (rotation % 90) == 0 else None
    rotNorm = rotNorm if rotNorm is None or rotNorm >= 0 else (4 + rotNorm)
    npRotation = rotNorm is not None and img.shape == (expectedDims[1], expectedDims[0])
    if npRotation:
        res = np.rot90(img, rotNorm)
    else:
        res = ndimage.interpolation.rotate(img, rotation, cval=cval, reshape=(img.shape != expectedDims))
    return res


def __compareRotatedImage(rotation, img1, img2, invert, arguments):
    res = __rotateImage(rotation, img1, img2.shape, cval=img2[0, 0])
    mask, analysis = __composeExpandImageMask(res, img2) if res.shape != img2.shape else __diffMask(res, img2, invert)
    res = __rotateImage(-rotation, mask, img1.shape, cval=255)
    return res, analysis


#      res = __resize(mask,(max(img2.shape[0],img1.shape[0]), max(img2.shape[1],img1.shape[1])))
#      res[res<0.00001] = 0
#      res[res>0] = 255
#      # now crop out the rotation difference, to make sure the original image is not modified
#      if img1.shape != res.shape:
#        diff = (res.shape[0]-img1.shape[0], res.shape[1]-img1.shape[1])
#        diff = (diff[0] if diff[0] > 0 else 0, diff[1] if diff[1] > 0 else 0)
#        res = res[diff[0]/2:res.shape[0]-((diff[0]/2) -diff[0]),diff[1]/2:res.shape[1]-((diff[1]/2) - diff[1])]


def __alignChannels(rawimg1, rawimg2,equalize_colors=False):
    return rawimg1.to_float(equalize_colors=equalize_colors).to_array(), rawimg2.to_float(equalize_colors=equalize_colors).to_array()

def __findBestMatch(big, small):
    """ Return a tuple describing the bounding box (xl,xh,yl,yh) with the most
        likely match to the small image.
    """
    if np.any(np.asarray([(x[1] - x[0]) for x in zip(small.shape, big.shape)]) < 0):
        return None
    result = cv2.matchTemplate(big, small, cv2.cv.CV_TM_SQDIFF_NORMED)
    mn, _, mnLoc, _ = cv2.minMaxLoc(result)
    tuple = (mnLoc[1], mnLoc[0], mnLoc[1] + small.shape[0], mnLoc[0] + small.shape[1])
    if (tuple[2] > big.shape[0] or tuple[3] > big.shape[1]):
        return None
    return tuple


def __composeCropImageMask(img1, img2, seamAnalysis=False):
    """ Return a masking where img1 is bigger than img2 and
        img2 is likely a crop of img1.
    """
    tuple = __findBestMatch(img1, img2)
    mask = None
    analysis = {}
    analysis['location'] = '(0,0)'
    if tuple is not None:
        dims = (0, img2.shape[0], 0, img2.shape[1])
        diffIm = np.zeros(img1.shape).astype('float32')
        diffIm[tuple[0]:tuple[2], tuple[1]:tuple[3]] = img2
        pinned = np.where(np.array(dims) == np.array(tuple))[0]
        analysis = img_analytics(img1, diffIm)
        analysis['location'] = str((int(tuple[0]), int(tuple[1])))
        dst = np.abs(img1 - diffIm)
        gray_image = np.zeros(img1.shape).astype('uint8')
        gray_image[dst > 0.0001] = 255
        mask = gray_image
        if len(pinned) >= 2 and seamAnalysis:
            diffIm2 = np.copy(img1).astype('float32')
            diffIm2[tuple[0]:tuple[2], tuple[1]:tuple[3]] = img2
            dst2 = np.abs(img1 - diffIm2)
            gray_image2 = np.zeros(img1.shape).astype('uint8')
            gray_image2[dst2 > 0.0001] = 255
            mask = __seamMask(gray_image2)
    else:
        mask = np.ones(img1.shape) * 255
    return abs(255 - mask).astype('uint8'), analysis


def __composeExpandImageMask(img1, img2):
    """ Return a masking where img1 is smaller than img2 and
        img2 contains img1.
    """
    tuple = __findBestMatch(img2, img1)
    mask = None
    analysis = {}
    if tuple is not None:
        diffIm = img2[tuple[0]:tuple[2], tuple[1]:tuple[3]]
        analysis = img_analytics(img1, diffIm)
        dst = np.abs(img1 - diffIm)
        gray_image = np.zeros(img1.shape).astype('uint8')
        gray_image[dst > 0.0001] = 255
        mask = gray_image
    else:
        mask = np.ones(img1.shape) * 255
    return abs(255 - mask).astype('uint8'), analysis


def __colorPSNR(z1, z2):
    d = (z1 - z2) ** 2
    sse = np.sum(d)
    mse = float(sse) / float(reduce(lambda x, y: x * y, d.shape))
    return 0.0 if mse == 0.0 else 20.0 * math.log10(255.0 / math.sqrt(mse))


def __sizeDiff(z1, z2):
    """
       z1 and z2 are expected to be PIL images
    """
    # size is inverted due to Image's opposite of numpy arrays
    return str((int(z2.size[1] - z1.size[1]),int( z2.size[0] - z1.size[0])))


def invertMask(mask):
    return mask.invert()

def convertToMask(im):
    """
      Takes an image and produce a mask where all black areas are white
    """
    return im.to_mask()


def __checkInterpolation(val):
    validVals = ['nearest', 'lanczos', 'bilinear', 'bicubic' or 'cubic']
    return val if val in validVals else 'nearest'


def alterMask(compositeMask, edgeMask, rotation=0.0, sizeChange=(0, 0), interpolation='nearest', location=(0, 0),
              transformMatrix=None, flip=None):
    res = compositeMask
    if transformMatrix is not None:
        res = __applyTransform(compositeMask, edgeMask, deserializeMatrix(transformMatrix))
    elif abs(rotation) > 0.001:
        res = __rotateImage(rotation,  res,
                            (compositeMask.shape[0] + sizeChange[0], compositeMask.shape[1] + sizeChange[1]), cval=255)
    elif flip is not None:
        res = cv2.flip(res, 1 if flip == 'horizontal' else (-1 if flip == 'both' else 0))
    if location != (0, 0):
        sizeChange = (-location[0], -location[1]) if sizeChange == (0, 0) else sizeChange
    expectedSize = (res.shape[0] + sizeChange[0], res.shape[1] + sizeChange[1])
    if location != (0, 0):
        upperBound = (res.shape[0] -location[0], res.shape[1] -location[1])
        res = res[location[0]:upperBound[0], location[1]:upperBound[1]]
    if expectedSize != res.shape:
        res = cv2.resize(res,(expectedSize[1],expectedSize[0]))
    return res

def alterReverseMask(donorMask, edgeMask, rotation=0.0, sizeChange=(0, 0), location=(0, 0),
              transformMatrix=None, flip=None):
    res = donorMask
    if transformMatrix is not None:
        res = __applyTransform(donorMask, edgeMask, deserializeMatrix(transformMatrix),invert=True)
    elif abs(rotation) > 0.001:
        res = __rotateImage(-rotation,  res,
                            (donorMask.shape[0] + sizeChange[0], donorMask.shape[1] + sizeChange[1]), cval=255)
    elif flip is not None:
        res = cv2.flip(res, 1 if flip == 'horizontal' else (-1 if flip == 'both' else 0))
    if location != (0, 0):
        sizeChange = (-location[0], -location[1]) if sizeChange == (0, 0) else sizeChange
    expectedSize = (res.shape[0] - sizeChange[0], res.shape[1] - sizeChange[1])
    if location != (0, 0):
        newRes = np.ones(expectedSize)*255
        upperBound = (res.shape[0] + location[0], res.shape[1] + location[1])
        newRes[location[0]:upperBound[0], location[1]:upperBound[1]] = res[0:(upperBound[0]-location[0]),0:(upperBound[1]-location[1])]
        res = newRes
    if expectedSize != res.shape:
        res = cv2.resize(res,(expectedSize[1],expectedSize[0]))
    return res

def __toMask(im):
    """
    Performs same functionality as convertToMask, but takes and returns np array
    """
    if len(im.shape) < 3:
        return im
    imGray = cv2.cvtColor(im, cv2.COLOR_RGB2GRAY)
    gray_image = np.ones(imGray.shape).astype('uint8')
    gray_image[imGray < 255] = 0
    gray_image = gray_image * 255
    if im.shape[2] == 4:
        gray_image[im[:, :, 3] == 0] = 255
    return gray_image

def mergeMask(compositeMask, newMask,level=0):
    if compositeMask.shape != newMask.shape:
        compositeMask = cv2.resize(compositeMask, (newMask.shape[1], newMask.shape[0]))
        newMask = ImageWrapper(newMask).to_mask().to_array()
    else:
        compositeMask = np.copy(compositeMask)
    compositeMask[newMask==0] = level
    return compositeMask


def img_analytics(z1, z2):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return {'ssim': compare_ssim(z1, z2, multichannel=False), 'psnr': __colorPSNR(z1, z2)}


def __diffMask(img1, img2, invert,args=None):
    dst = np.abs(img1 - img2)
    gray_image = np.zeros(img1.shape).astype('uint8')
    difference = float(args['tolerance']) if args is not None and 'tolerance' in args else 0.0001
    gray_image[dst > difference] = 255
    analysis = img_analytics(img1, img2)
    return (np.array(gray_image) if invert else (255 - np.array(gray_image))), analysis


def fixTransparency(img):
    return img.apply_transparency()

def __findNeighbors(paths, next_pixels):
    newpaths = list()
    s = set()
    for path in paths:
        x = path[len(path) - 1]
        for i in np.intersect1d(np.array([x - 1, x, x + 1]), next_pixels):
            if i not in s:
                newpaths.append(path + [i])
                s.add(i)
    return newpaths


def __findVerticalSeam(mask):
    paths = list()
    for candidate in np.where(mask[0, :] > 0)[0]:
        paths.append([candidate])
    for x in range(1, mask.shape[0]):
        paths = __findNeighbors(paths, np.where(mask[x, :] > 0)[0])
    return paths


def __findHorizontalSeam(mask):
    paths = list()
    for candidate in np.where(mask[:, 0] > 0)[0]:
        paths.append([candidate])
    for y in range(1, mask.shape[1]):
        paths = __findNeighbors(paths, np.where(mask[:, y] > 0)[0])
    return paths


def __seamMask(mask):
    seams = __findVerticalSeam(mask)
    if len(seams) > 0:
        first = seams[0]
        # should compare to seams[-1].  this would be accomplished by
        # looking at the region size of the seam. We want one of the first or last seam that is most
        # centered
        mask = np.zeros(mask.shape)
        for i in range(len(first)):
            mask[i, first[i]] = 255
        return mask
    else:
        seams = __findHorizontalSeam(mask)
        if len(seams) == 0:
            return mask
        first = seams[0]
        # should compare to seams[-1]
        mask = np.zeros(mask.shape)
        for i in range(len(first)):
            mask[first[i], i] = 255
        return mask


def __add_edge(edges, edge_points, points, i, j):
    if (i, j) in edges or (j, i) in edges:
        return
    edges.add((i, j))
    edge_points.extend([points[i],points[j]])


def __calc_alpha2(alpha, points):
    from scipy.spatial import Delaunay

    tri = Delaunay(points)
    edges = set()
    edge_points = []
    # loop over triangles:
    for ia, ib, ic in tri.vertices:
        pa = points[ia]
        pb = points[ib]
        pc = points[ic]
        a = np.sqrt((pa[0] - pb[0]) ** 2 + (pa[1] - pb[1]) ** 2)
        b = np.sqrt((pb[0] - pc[0]) ** 2 + (pb[1] - pc[1]) ** 2)
        c = np.sqrt((pc[0] - pa[0]) ** 2 + (pc[1] - pa[1]) ** 2)
        s = (a + b + c) / 2.0
        area = np.sqrt(s * (s - a) * (s - b) * (s - c))
        circum_r = a * b * c / (4.0 * area)
        if circum_r < 10.0/alpha:
            __add_edge(edges, edge_points, points, ia, ib)
            __add_edge(edges, edge_points, points, ib, ic)
            __add_edge(edges, edge_points, points, ic, ia)
    return edge_points

def grayToRGB(frame):
    """
      project gray into Green
    """
    #  cv2.cvtColor(result, cv2.COLOR_GRAY2BGR))
    result = np.zeros((frame.shape[0], frame.shape[1], 3))
    if len (frame.shape) == 2:
        result[:, :, 1] = frame
    else:
        summary = np.zeros((frame.shape[0], frame.shape[1]))
        for d in range(frame.shape[2]):
            summary[:,:] += frame[:,:,d]
        summary[summary>0] = 255
        result[:,:,1] =summary
    return result.astype('uint8')

def composeVideoMaskName(maskprefix, starttime, suffix):
    """
    :param maskprefix:
    :param starttime:
    :param suffix:
    :return: A mask file name using the provided components
    """
    return maskprefix + '_mask_' + str(starttime) + '.' + suffix

def convertToMP4(file_name):
    fn = file_name[:file_name.rfind('.')] + '.mp4'
    if os.path.exists(fn):
        if os.stat(file_name).st_mtime < os.stat(fn).st_mtime:
            return fn
        else:
            os.remove(fn)
    reader = GrayBlockReader(file_name,convert=True)
    while True:
        mask = reader.read()
        if mask is None:
            break
    return fn

class GrayBlockReader:

    pos = 0
    convert = False
    writer = None

    def __init__(self,  filename, convert=False):
        self.filename = filename
        self.h_file = h5py.File(filename, 'r')
        self.dset = self.h_file.get('masks').get('masks')
        self.fps = self.h_file.attrs['fps']
        self.start_time = self.h_file.attrs['start_time']
        self.convert = convert
        self.writer = GrayFrameWriter(self.h_file.attrs['prefix'],
                                      self.fps) if self.convert else DummyWriter()

    def current_frame_time(self):
        return self.start_time + (self.pos*self.fps)

    def read(self):
        if self.dset is None:
            return None
        if self.pos >= self.dset.shape[0]:
            self.dset = None
            return None
        mask = self.dset[self.pos,:,:]
        self.writer.write(mask,self.current_frame_time())
        self.pos += 1
        return mask.astype('uint8')

    def release(self):
        None

    def close(self):
        self.h_file.close()
        if self.writer is not None:
            self.writer.close()

class DummyWriter:
    def write(self, mask, mask_time):
        None

    def close(self):
        None

class GrayBlockWriter:
    """
      Write Gray scale (Mask) images to a compressed block file
      """
    h_file = None
    suffix = 'hdf5'
    filename = None
    fps = 0
    mask_prefix = None
    pos = 0
    dset = None

    def __init__(self, mask_prefix, fps):
        self.fps = fps
        self.mask_prefix = mask_prefix

    def write(self, mask, mask_time):
        if self.h_file is None:
            self.filename = composeVideoMaskName(self.mask_prefix,mask_time,self.suffix)
            if os.path.exists(self.filename):
                os.remove(self.filename)
            self.h_file = h5py.File(self.filename, 'w')
            self.h_file.attrs['fps'] = self.fps
            self.h_file.attrs['prefix'] = self.mask_prefix
            self.h_file.attrs['start_time'] = mask_time
            self.grp = self.h_file.create_group('masks')
            self.dset = self.grp.create_dataset("masks",
                                                (10,mask.shape[0], mask.shape[1]),
                                                compression="gzip",
                                                chunks=True,
                                                maxshape=(None, mask.shape[0], mask.shape[1]))
            self.pos = 0
        if self.dset.shape[0] < (self.pos+1):
             self.dset.resize((self.pos+1,mask.shape[0], mask.shape[1]))
        new_mask = mask
        if len(mask.shape)>2:
            new_mask = np.ones((mask.shape[0],mask.shape[1]))*255
            for i in range(mask.shape[2]):
                new_mask[mask[:,:,i]>0] = 0
        self.dset[self.pos,:,:] = new_mask
        self.pos+=1

    def get_file_name(self):
        return self.filename

    def close(self):
        self.release()

    def release(self):
        self.grp = None
        self.dset = None
        if self.h_file is not None:
            self.h_file.close()
        self.h_file = None


class GrayFrameWriter:
    """
    Write Gray scale (Mask) video images
    """
    capOut = None
    codec = 'fmp4'
    suffix = 'mp4'
    fourcc = cv2.cv.CV_FOURCC(*codec)
    filename = None
    fps = 0
    mask_prefix = None

    def __init__(self, mask_prefix, fps):
        self.fps = fps
        self.mask_prefix = mask_prefix

    def write(self,mask,mask_time):
        if self.capOut is None:
            self.filename = composeVideoMaskName(self.mask_prefix, mask_time, self.suffix)
            self.capOut = cv2.VideoWriter(self.filename,
                                          self.fourcc,
                                          self.fps,
                                          (mask.shape[1],mask.shape[0]),
                                          False)
        #rgb = grayToRGB(mask)
        self.capOut.write(mask.astype('uint8'))

    def close(self):
        if self.capOut is not None:
          self.capOut.release()
        self.capOut = None

    def release(self):
        self.close()

class GrayFrameReader:
    """
    Write Gray scale (Mask) video images
    """
    capOut = None
    codec = 'mp4v'
    suffix = 'mp4'
    fourcc = cv2.cv.CV_FOURCC(*codec)
    filename = None
    fps = 0
    mask_prefix = None

    def __init__(self, mask_prefix, fps):
        self.fps = fps
        self.mask_prefix = mask_prefix

    def write(self,mask,mask_time):
        if self.capOut is None:
            self.filename = composeVideoMaskName(self.mask_prefix, mask_time, self.suffix)
            self.capOut = cv2.VideoWriter(self.filename,
                                          self.fourcc,
                                          self.fps,
                                          (mask.shape[1],mask.shape[0]),
                                          False)
        self.capOut.write(grayToRGB(mask))

    def close(self):
        if self.capOut is not None:
          self.capOut.release()
        self.capOut = None

    def release(self):
        self.close()
