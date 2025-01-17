from maskgen import tool_set
import unittest
import numpy as np
from maskgen import image_wrap
from test_support import TestSupport
import sys



class TestToolSet(TestSupport):


    def test_diff(self):
        args = {'smoothing': 3, 'mode':'bgr', 'aggregate':'max','filling':'morphology'}
        a = np.random.randint(0,255,(255,255,3)).astype('int16')
        b = np.random.randint(0, 255, (255, 255, 3)).astype('int16')
        m = tool_set.mediatedCompare(a,b, arguments= args)

    def test_filetype(self):
        self.assertEquals(tool_set.fileType(self.locateFile('images/hat.jpg')), 'image')
        self.assertEquals(tool_set.fileType(self.locateFile('images/sample.json')), 'text')
        f = open('test.log', 'w+')
        f.close()
        self.addFileToRemove('test.log')
        self.assertEquals(tool_set.fileType(self.locateFile('test.log')), 'text')
        self.assertEquals(tool_set.fileType(self.locateFile('tests/videos/sample1.mov')), 'video')
        self.assertEquals(tool_set.fileType('foo.dng.zip'), 'zip')
        self.assertEquals(tool_set.fileType('foo.jpg.zip'), 'zip')
        self.assertEquals(tool_set.fileType('foo.png.zip'), 'zip')
        self.assertEquals(tool_set.fileType('foo.oh.zip'), 'collection')
        self.assertEquals(tool_set.fileType('foo.newgate.zip'), 'collection')

    def test_md5(self):
        all_md5 = tool_set.md5_of_file(self.locateFile('tests/videos/sample1.mov'))
        parts_md5 = tool_set.md5_of_file(self.locateFile('tests/videos/sample1.mov'),load_size=1000)
        self.assertEqual(all_md5,parts_md5)

    def test_filetypes(self):
        self.assertTrue(("mov files", "*.mov") in tool_set.getFileTypes())
        self.assertTrue(("zipped masks", "*.tgz") in tool_set.getMaskFileTypes())

    def test_zip(self):
        import os
        filename = self.locateFile('tests/zips/raw.zip')
        self.addFileToRemove(os.path.join(os.path.dirname(filename), 'raw.png'))
        img = tool_set.openImage(filename,tool_set.getMilliSecondsAndFrameCount('2'),preserveSnapshot=True)
        self.assertEqual((5796, 3870),img.size)
        tool_set.condenseZip(filename,keep=1)
        self.addFileToRemove(os.path.join(os.path.dirname(filename),'raw_c.zip'))
        contents = tool_set.getContentsOfZip(os.path.join(os.path.dirname(filename),'raw_c.zip'))
        self.assertTrue('59487443539401a4d83512edaab3c1b2.cr2' in contents)
        self.assertTrue('7d1800a38ca7a22021bd94e71b6e0f42.cr2' in contents)
        self.assertTrue(len(contents) == 2)


    def test_rotate(self):
        import cv2
        from maskgen import cv2api
        img1 = np.zeros((100,100),dtype=np.uint8)
        img1[20:50,40:50] = 1
        mask = np.ones((100,100),dtype=np.uint8)*255
        img1[20:50,40] = 2
        img = tool_set.applyRotateToCompositeImage(img1, 90, (50,50))
        self.assertTrue(sum(sum(img1-img))>40)
        img = tool_set.applyRotateToCompositeImage(img,-90,(50,50))
        self.assertTrue(sum(sum(img1-img)) <2)
        img = tool_set.applyRotateToComposite(-90, img1,  np.zeros((100,100),dtype=np.uint8), img1.shape, local=True)
        self.assertTrue(sum(img[40,:]) == sum(img1[:,40]))
        self.assertTrue(sum(img[40, :]) == 60)
        M = cv2.getRotationMatrix2D((35,45), -90, 1.0)
        img = cv2.warpAffine(img1, M, (img.shape[1], img.shape[0]),
                                     flags=cv2api.cv2api_delegate.inter_linear)

        mask[abs(img - img1) > 0] = 0
        img[10:15,10:15]=3
        img3 = tool_set.applyRotateToComposite(90, img, mask, img1.shape, local=True)
        self.assertTrue(np.all(img3[10:15,10:15]==3))
        img3[10:15, 10:15] = 0

    def testCropCompare(self):
        import cv2
        pre = tool_set.openImageFile(self.locateFile('tests/images/prefill.png')).to_array()
        post = pre[10:-10,10:-10]
        resized_post = cv2.resize(post, (pre.shape[1],pre.shape[0]))
        mask, analysis = tool_set.cropResizeCompare(pre,resized_post, arguments={'crop width':pre.shape[1]-20,'crop height':pre.shape[0]-20})
        self.assertEquals((10,10), tool_set.toIntTuple(analysis['location']))

    def test_fileMask(self):
        pre = tool_set.openImageFile(self.locateFile('tests/images/prefill.png'))
        post = tool_set.openImageFile(self.locateFile('tests/images/postfill.png'))
        mask,analysis,error = tool_set.createMask(pre,post,invert=False,arguments={'tolerance' : 2500})
        withtolerance = sum(sum(mask.image_array))
        mask.save(self.locateFile('tests/images/maskfill.png'))
        mask, analysis,error = tool_set.createMask(pre, post, invert=False)
        withouttolerance = sum(sum(mask.image_array))
        mask, analysis ,error= tool_set.createMask(pre, post, invert=False, arguments={'tolerance': 2500,'equalize_colors':True})
        mask.save(self.locateFile('tests/images/maskfillt.png'))
        withtoleranceandqu = sum(sum(mask.image_array))
        self.assertTrue(withouttolerance < withtolerance)
        self.assertTrue(withtolerance <= withtoleranceandqu)

    def test_map(self):
            img1 = np.random.randint(0,255,size=(100,120)).astype('uint8')
            mask = np.ones((100,120))
            src_pts = [(x, y) for x in xrange(20, 30, 1) for y in xrange(50, 60, 1)]
            dst_pts = [(x, y) for x in xrange(55, 65, 1) for y in xrange(15, 25, 1)]
            result =tool_set._remap(img1,mask,src_pts,dst_pts)
            self.assertTrue(np.all(result[55:65,15:25] == img1[20:30,50:60]))

    def test_time_format(self):
        t = tool_set.getDurationStringFromMilliseconds(100001.111)
        self.assertEqual('00:01:40.001111',t)

    def test_timeparse(self):
        t, f = tool_set.getMilliSecondsAndFrameCount('00:00:00')
        self.assertEqual(1, f)
        self.assertEqual(0, t)
        t, f = tool_set.getMilliSecondsAndFrameCount('1')
        self.assertEqual(1, f)
        self.assertEqual(0, t)
        self.assertTrue(tool_set.validateTimeString('03:10:10.434'))
        t,f = tool_set.getMilliSecondsAndFrameCount('03:10:10.434')
        self.assertEqual(0, f)
        self.assertEqual(1690434, t)
        t, f = tool_set.getMilliSecondsAndFrameCount('03:10:10:23')
        self.assertFalse(tool_set.validateTimeString('03:10:10:23'))
        self.assertEqual(23,f)
        self.assertEqual(1690000, t)
        t, f = tool_set.getMilliSecondsAndFrameCount('03:10:10:A', defaultValue=(0,0))
        self.assertFalse(tool_set.validateTimeString('03:10:10:A'))
        self.assertEqual((0,0), (t,f))
        time_manager = tool_set.VidTimeManager(startTimeandFrame=(1000,2),stopTimeandFrame=(1003,4))
        time_manager.updateToNow(999)
        self.assertTrue(time_manager.isBeforeTime())
        time_manager.updateToNow(1000)
        self.assertTrue(time_manager.isBeforeTime())
        time_manager.updateToNow(1001)
        self.assertTrue(time_manager.isBeforeTime())
        time_manager.updateToNow(1002)
        self.assertFalse(time_manager.isBeforeTime())
        self.assertFalse(time_manager.isPastTime())
        time_manager.updateToNow(1003)
        self.assertFalse(time_manager.isPastTime())
        time_manager.updateToNow(1004)
        self.assertFalse(time_manager.isPastTime())
        time_manager.updateToNow(1005)
        self.assertFalse(time_manager.isPastTime())
        time_manager.updateToNow(1006)
        self.assertFalse(time_manager.isPastTime())
        time_manager.updateToNow(1007)
        self.assertFalse(time_manager.isPastTime())
        time_manager.updateToNow(1008)
        self.assertTrue(time_manager.isPastTime())
        self.assertEqual(9,time_manager.getEndFrame() )
        self.assertEqual(4, time_manager.getStartFrame())

        time_manager = tool_set.VidTimeManager(startTimeandFrame=(999, 2), stopTimeandFrame=None)
        time_manager.updateToNow(999)
        self.assertTrue(time_manager.isBeforeTime())
        time_manager.updateToNow(1000)
        self.assertTrue(time_manager.isBeforeTime())
        time_manager.updateToNow(1001)
        self.assertFalse(time_manager.isBeforeTime())
        self.assertEqual(3, time_manager.getEndFrame())
        self.assertEqual(3, time_manager.getStartFrame())

    def test_opacity_analysis(self):
        # need to redo with generated data.
        initialImage = image_wrap.openImageFile(self.locateFile('tests/images/pre_blend.png'))
        finalImage = image_wrap.openImageFile(self.locateFile('tests/images/post_blend.png'))
        mask = image_wrap.openImageFile(self.locateFile('tests/images/blend_mask.png'))
        donorMask = image_wrap.openImageFile(self.locateFile('tests/images/donor_to_blend_mask.png'))
        donorImage = image_wrap.openImageFile(self.locateFile('tests/images/donor_to_blend.png'))
        result = tool_set.generateOpacityImage(initialImage.to_array(), donorImage.to_array(), finalImage.to_array(), mask.to_array(),
                                               donorMask.to_array(),None)
        min = np.min(result)
        max = np.max(result)
        result = (result - min)/(max-min) * 255.0

    def test_gray_writing(self):
        import os
        import sys
        import time
        s  = time.clock()
        writer = tool_set.GrayBlockWriter('test_ts_gw', 29.97002997)
        mask_set = list()
        for i in range(255):
            mask = np.random.randint(255, size=(1090, 1920)).astype('uint8')
            mask_set.append(mask)
            writer.write(mask, 33.3666666667*i,i+1)
        for i in range(300,350):
            mask = np.random.randint(255, size=(1090, 1920)).astype('uint8')
            mask_set.append(mask)
            writer.write(mask, 33.3666666667*i, i + 1)
        writer.close()
        fn = writer.get_file_name()
        reader = tool_set.GrayBlockReader(fn, end_frame=305)
        pos = 0
        while True:
            mask = reader.read()
            if mask is None:
                break
            compare = mask == mask_set[pos]
            self.assertEqual(mask.size,sum(sum(compare)))
            if pos == 255:
                self.assertEqual(301,reader.current_frame()-1)
            pos += 1

        reader.close()
        self.assertEqual(305, pos)
        print time.clock()- s
        suffix = 'm4v'
        if sys.platform.startswith('win'):
            suffix = 'avi'
        filename  = tool_set.convertToVideo(fn)
        self.assertEquals('test_ts_gw_mask_0.0.' + suffix, filename)
        self.assertTrue(os.path.exists(filename))

        size = tool_set.openImage(filename, tool_set.getMilliSecondsAndFrameCount('00:00:01')).size
        self.assertTrue(size == (1920,1090))
        os.remove(filename)
        os.remove(fn)

    def test_global_transform_analysis(self):
        from maskgen.image_wrap import ImageWrapper
        analysis = {}
        mask = np.random.randint(0,2,(1000, 1000), dtype=np.uint8)
        mask[mask>0] = 255
        tool_set.globalTransformAnalysis(analysis, ImageWrapper(mask), ImageWrapper(mask), mask=mask,
                                         linktype='image.image',
                                         arguments={}, directory='.')
        self.assertEquals('yes', analysis['global'])

        mask = np.zeros((1000,1000),dtype=np.uint8)
        mask[0:30,0:30] = 255
        tool_set.globalTransformAnalysis(analysis, ImageWrapper(mask), ImageWrapper(mask), mask=mask, linktype='image.image', arguments={}, directory='.')
        self.assertEquals('no',analysis['global'])
        self.assertEquals('small', analysis['change size category'])
        mask = np.zeros((1000, 1000), dtype=np.uint8)
        mask[0:75, 0:75] = 255
        tool_set.globalTransformAnalysis(analysis, ImageWrapper(mask), ImageWrapper(mask), mask=mask, linktype='image.image',
                                                    arguments={}, directory='.')
        self.assertEquals('no', analysis['global'])
        self.assertEquals('medium', analysis['change size category'])
        mask[0:100, 0:100] = 255
        tool_set.globalTransformAnalysis(analysis, ImageWrapper(mask), ImageWrapper(mask), mask=mask, linktype='image.image',
                                                    arguments={}, directory='.')
        self.assertEquals('no', analysis['global'])
        self.assertEquals('large', analysis['change size category'])
        tool_set.globalTransformAnalysis(analysis, ImageWrapper(mask), ImageWrapper(mask), mask=mask, linktype='image.image',
                                                    arguments={}, directory='.')

    def test_SIFT(self):
        from maskgen.image_wrap import ImageWrapper
        img1 = ImageWrapper(np.random.randint(0,255,(4000,5000,3),dtype='uint8'))
        img2 = ImageWrapper(np.random.randint(0,255,(8000,8000,3),dtype='uint8'))
        img2.image_array[1000:2000,1000:2000,:] = img1.image_array[2000:3000,2000:3000,:]
        mask1 = ImageWrapper(np.zeros((4000,5000),dtype='uint8'))
        mask1.image_array[2000:3000,2000:3000] = 255
        mask2 = ImageWrapper(np.zeros((8000, 8000), dtype='uint8'))
        mask2.image_array[1000:2000,1000:2000] = 255

        features = tool_set.getMatchedSIFeatures(img1, img2, mask1=mask1, mask2=mask2, arguments={'homography max matches': '2000', 'homography': 'RANSAC-4'})

        img1 = ImageWrapper(np.random.randint(0, 65535, (4000, 5000, 3), dtype='uint16'))
        img2 = ImageWrapper(np.random.randint(0, 65535, (8000, 8000, 3), dtype='uint16'))
        img2.image_array[1000:2000, 1000:2000, :] = img1.image_array[2000:3000, 2000:3000, :]
        mask1 = ImageWrapper(np.zeros((4000, 5000), dtype='uint8'))
        mask1.image_array[2000:3000, 2000:3000] = 255
        mask2 = ImageWrapper(np.zeros((8000, 8000), dtype='uint8'))
        mask2.image_array[1000:2000, 1000:2000] = 255

        features = tool_set.getMatchedSIFeatures(img1, img2, mask1=mask1, mask2=mask2, arguments={'homography max matches': '2000', 'homography': 'RANSAC-4'})

    def testSIFCheck(self):
        good_transform = {
            'c': 3,
            'r': 3,
            'r0': [0.00081380729604268976, -1.0000367374350523, 449.94975699899271],
            'r1': [1.0031702728345473, 0.0016183966076946312, -0.30844081957395447],
            'r2': [3.1676664384933143e-06, 9.8915322781393527e-06, 1.0]
        }
        bad_transform = {
            "c": 3,
            "r": 3,
            "r0": [-3.0764931522976067, 3.2522108810844577, 6167.618028229406],
            "r1": [-1.0467579456165736, 1.1073481736839244, 2098.303251843684],
            "r2": [-0.0004988685498607748, 0.0005275910530971817, 1.0]
        }
        self.assertTrue(tool_set.isHomographyOk(tool_set.deserializeMatrix(good_transform),450,450))
        self.assertFalse(tool_set.isHomographyOk(  tool_set.deserializeMatrix(bad_transform),8000,5320))

    def test_time_stamp(self):
        v1 = self.locateFile('tests/images/test.png')
        v2 = self.locateFile('tests/images/donor_to_blend.png')
        v3 = self.locateFile('tests/images/test_time_change.png')
        self.assertTrue(len(tool_set.dateTimeStampCompare(v1, v1))==0)
        self.assertFalse(len(tool_set.dateTimeStampCompare(v1, v2))==0)
        self.assertTrue(len(tool_set.dateTimeStampCompare(v1, v3))==0)


    def test_compare(self):
        from maskgen import tool_set
        wrapper1 = image_wrap.openImageFile(self.locateFile('tests/images/pre_blend.png'))
        arr2 = np.copy(wrapper1.image_array)
        for x in np.random.randint(1,arr2.shape[0]-1,100):
            for y in np.random.randint(1, arr2.shape[1] - 1, 100):
                arr2[x,y,1] = arr2[x,y,1] + np.random.randint(-20,20)
        arr2[100:200,100:200,2] = arr2[100:200,100:200,2] - 25
        wrapper2 = image_wrap.ImageWrapper(arr2)

        args = [{'aggregate': 'luminance', 'minimum threshold': 3, "weight": 4},
                {'aggregate': 'luminance', 'minimum threshold': 3, "weight": 1},
                {'aggregate': 'max'}]
        for arg in args:
            result = tool_set.mediatedCompare(wrapper1.to_array().astype('int16'),
                                              wrapper2.to_array().astype('int16'),
                                              arguments=arg)
            self.assertTrue(np.all(result[0][100:200,100:200] == 255))
            result[0][100:200, 100:200] = 0
            self.assertTrue(np.all(result[0] == 0))
        #image_wrap.ImageWrapper(result[0]).save('/Users/ericrobertson/Downloads/foo_max.png')



if __name__ == '__main__':
    unittest.main()
