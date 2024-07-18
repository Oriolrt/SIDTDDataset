from .image_augmenter import ImageAugmenter


import numpy as np, pandas as pd, copy, torch, random, os

from tqdm import tqdm
from random import choice
from torch.autograd import Variable

import cv2
import tqdm
import torch
import imageio

from SIDTD.utils.transforms import CopyPaste, CropReplace, Inpainting, read_json

class Binary(object):
    def __init__(self, batch_size, image_size):
        """
        path: dataset path folder
        batch_size: the output is (2 * batch size, 1, image_size, image_size)
                    X[i] & X[i + batch_size] are the pair
        image_size: size of the image
        load_file: json file dict with split data information
        ---------------------
        Data Augmentation Parameters:
            flip: here flipping both the images in a pair
            scale: x would scale image by + or - x%
            rotation_deg
            shear_deg
            translation_px: in both x and y directions
        """
       
            

                
        self.image_size = image_size
        self.batch_size = batch_size

        self.mean_pixel = 0.5 #self.compute_mean()# used later for mean subtraction
        
        
        flip = True
        scale = 0.2
        rotation_deg = 20
        shear_deg = 10
        translation_px = 5
        self.augmentor = ImageAugmenter(image_size, image_size, channel_is_first_axis=True,
                                        hflip=flip, vflip=flip,
                                        scale_to_percent=1.0 + scale, rotation_deg=rotation_deg, shear_deg=shear_deg,
                                        translation_x_px=translation_px, translation_y_px=translation_px)


                
        
    def compute_mean(self):
        """
        Time consuming, ToDo: load precalculated if it exists.
        """
        count_images = 0
        # Read al the banknote images to comput the mean 
        for folder in tqdm(self.folders):
            for real_or_fake in self.images_dict[folder]:
                for image_path in self.images_dict[folder][real_or_fake]:
                
                    image = cv2.resize(imageio.imread(image_path), (self.image_size, self.image_size))
                    #initialize variable to compute the mean
                    if count_images == 0:
                        if image.shape[-1] == 3:
                            mean_image = np.zeros_like(image, dtype = np.float32())
                        else:
                            mean_image = np.zeros_like(image[...,:-1])
                    if image.shape[-1] == 3:
                        mean_image += image
                    else:
                        mean_image += image[...,:-1]
                    
                    count_images += 1
        mean_image = mean_image/count_images
        return np.moveaxis(mean_image, -1, 0)/255.0    


class Batcher(Binary):
    def __init__(self, opt, paths_splits, path_img):
        Binary.__init__(self, opt.batchSize, opt.imageSize)

        self.paths_splits = paths_splits
        self.faker_data_augmentation = opt.faker_data_augmentation
        self.shift_copy = opt.shift_copy
        self.shift_crop = opt.shift_crop
        self.image_size = opt.imageSize
        self.batch_size = opt.batchSize     
        self.path_img = path_img


    def fetch_batch(self, part, labels: str = None, image_paths: str = None):

        batch_size = self.batch_size

        if part == 'test':
            X, Y = self._fetch_eval(part, labels, image_paths, batch_size)   # batch generator for test set
        else:
            X, Y = self._fetch_batch(part, batch_size)                       # batch generator for train and validation set
        X = Variable(torch.from_numpy(X))

        X1 = X[:batch_size]  # (B, c, h, w)
        X2 = X[batch_size:]  # (B, c, h, w)

        X = torch.stack([X1, X2], dim=1)  # (B, 2, c, h, w)

        Y = Variable(torch.from_numpy(Y))

        return X, Y

    def _fetch_batch(self, part, batch_size: int = None):

        ''' 
            To load a batch of data into the model. 
            Every image in support set is composed of genuine document.
            Labels depend on the labels of images in query set. 
            Hence, the model compare a genuine document with a fake or genuine document, so the model must find out the label of the images in the query set.
            
            Query Set     Support Set     Labels
            Img 1      |  True image 1    1 if Img fake, else 0

            Img n      |  True image n    1 if Img fake, else 0
        '''

        paths_splits = self.paths_splits[part]
        
        image_size = self.image_size

        #build the input pairs
        X = np.zeros((2 * batch_size, 3, image_size, image_size), dtype='uint8')
        y = np.zeros((batch_size, 1), dtype='int32')
        
        for i in range(batch_size):
            idx1 = choice(np.arange(len(paths_splits['reals']['path'])))
            img_real = paths_splits['reals']['path'][idx1]
            X[i] = self.read_image(img_real, image_size)
            if i < batch_size//2 : 
                # choose one real image
                idx2 = choice(np.arange(len(paths_splits['reals']['path'])))
                img_real = paths_splits['reals']['path'][idx2]
                X[i + batch_size] = self.read_image(img_real, image_size)
                y[i] = 0

            elif (i >= batch_size//2) and (i < (3*batch_size//4)): 
                # choose one fake image
                idx2 = choice(np.arange(len(paths_splits['fakes']['path'])))
                img_fake = paths_splits['fakes']['path'][idx2]
                X[i + batch_size] = self.read_image(img_fake, image_size)
                y[i] = 1
            
            else:
                # choose one fake image
                if not self.faker_data_augmentation:
                    idx2 = choice(np.arange(len(paths_splits['fakes']['path'])))
                    img_fake = paths_splits['fakes']['path'][idx2]
                
                else:
                    # choose one fake image
                    if part == 'val':
                        idx2 = choice(np.arange(len(paths_splits['fakes']['path'])))
                        img_fake = paths_splits['fakes']['path'][idx2]
                    # PERFORM FORGERY AUGMENTATION ON GENUINE DOCUMENT
                    else:
                        idx2 = choice(np.arange(len(paths_splits['reals']['path'])))   # choose one genuine image to falsify on-the-fly
                        path_img_real = paths_splits['reals']['path'][idx2]
                        img_real = cv2.imread(path_img_real)
                        
                        id_country = path_img_real.split('/')[-1][:3]    # ID's country
                        path = 'split_kfold/clip_cropped_MIDV2020/annotations/annotation_' + id_country + '.json' 
                        annotations = read_json(path)   # read json with document annotations of fields area
                        
                        l_fake_type = ['crop', 'inpainting', 'copy']
                        fake_type = choice(l_fake_type)   # randomly draw one forgery techniques among: copy paste, crope & replace and inpainting
                        # perform copy pasting
                        if fake_type == 'copy':
                            img_fake = CopyPaste(img_real, annotations, self.shift_copy)

                        # perform inpainting
                        elif fake_type == 'inpainting':
                            img_fake = Inpainting(img_real, annotations, id_country)

                        # perform crop & replace
                        elif fake_type == 'crop':

                            if id_country in ['rus', 'grc']:
                                list_image_field = ['image']    # Russian and greek ID doesn't have signature on ID
                            else:
                                list_image_field = ['image', 'signature']
                        
                            dim_issue = True
                            # Loop until crop & replace does not create dimension issue
                            while dim_issue:
                                # choose a document to crop the image or signature
                                img_path_template_target = choice(self.path_img)
                                image_target = cv2.imread(img_path_template_target)

                                country_target = img_path_template_target.split('/')[-1][:3]
                                if country_target in ['rus', 'grc']:
                                    if 'signature' in list_image_field:
                                        list_image_field.remove('signature')

                                path = 'split_kfold/clip_cropped_MIDV2020/annotations/annotation_' + country_target + '.json'
                                annotations_target = read_json(path)
                            
                                img_fake, dim_issue = CropReplace(img_real, annotations, image_target, annotations_target, list_image_field, self.shift_crop)
                        

                
                X[i + batch_size] = self.read_image(img_fake, image_size)   # reshape image to fix image size
                y[i] = 1

        if part == 'train':
            X = self.augmentor.augment_batch(X)   # perform classic data augmentation
        if part == 'val':
            X = X / 255.0   # normalize
        X = X.astype("float32")

        return X, y

    def _fetch_eval(self, part, labels, image_paths, batch_size):
        ''' 
            To load a batch of test data into the model so that 2-way one-shot classification 
            can be conducted, match each test image with every image in support set:
            
            Test     Support Set     Labels
            Img 1  |  True image 1    1 if Img fake, else 0

            Img n  |  True image n    1 if Img fake, else 0
        '''

        paths_splits = self.paths_splits[part]
        
        image_size = self.image_size

        #build the input pairs
        X = np.zeros((2 * batch_size, 3, image_size, image_size), dtype='uint8')
        y = np.zeros((batch_size, 1), dtype='int32')
        i = 0 
        for lbl, img in zip(labels, image_paths):
            idx = choice(np.arange(len(paths_splits['reals']['path'])))
            img_real = paths_splits['reals']['path'][idx]
            X[i] = self.read_image(img_real, image_size)
            X[i + batch_size] = self.read_image(img, image_size)
            if lbl == 'reals':
                y[i] = 0
            if lbl == 'fakes':
                y[i] = 1
            i = i + 1

        
        X = X / 255.0
        X = X.astype("float32")

        return X, y
    
    def reshape_img(self, image, image_size):
        if image.shape[-1]>=4:
            image = image[...,:-1]
        image = cv2.resize(image, (image_size,image_size))
        
        return np.moveaxis(image, -1, 0) 

    def read_image(self, image_path, image_size):
            image = imageio.imread(image_path)
            if image.shape[-1]>=4:
                image = image[...,:-1]
            image = cv2.resize(image, (image_size,image_size))
            
            return np.moveaxis(image, -1, 0) 

