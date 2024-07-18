import cv2

from torch.utils.data import Dataset
from .transforms import  *


class TrainDataset(Dataset):
    """ Classic Batch Data Generator. 
    Input:  Image path in csv
    Output: image in array format + label
    You can choose to perform data augmentation by setting a function with the transform argument.
    """
    def __init__(self, paths, ids, transform=None, dataset_crop=False):
        self.paths = paths
        self.ids = ids
        self.transform = transform
        self.dataset_crop = dataset_crop
    
    def __len__(self):
        return len(self.paths)
    
    def __getitem__(self, idx):
        file_path = self.paths[idx]
        label = self.ids[idx]
        image = cv2.imread(file_path)
    
        try:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        except:
            print(file_path)
        if self.dataset_crop:
            sx, sy, _ = image.shape
            sx2 = int(sx/2)
            sy2 = int(sy/2)
            image = image[sx2-250:sx2+250, sy2-250:sy2+250, :]
            
        if self.transform:
            augmented = self.transform(image=image)
            image = augmented['image']
    
        return image, label
    

flatten = lambda l: [item for sublist in l for item in sublist]


class TrainDatasets_augmented(Dataset):
    """
    This dataset class allows mini-batch formation pre-epoch, for greater speed. 
    This dataloader generate batch composed of 25% of fake data, 25% of fake data generated on-the-fly, 50% of real data.
    """
    def __init__(self, args, image_dict, path_img, transform=None):
        """
        Args:
            image_dict: two-level dict, `super_dict[super_class_id][class_id]` gives the list of
                        image paths having the same super-label and class label
        """
        self.image_dict = image_dict
        self.dataset_name = args.dataset
        if args.model in ['vit_large_patch16_224', 'efficientnet-b3', 'resnet50']:
            self.batch_size = args.batch_size
        else:
            self.batch_size = args.train_batch_size
        self.faker_data_augmentation = args.faker_data_augmentation
        self.shift_crop = args.shift_crop
        self.shift_copy = args.shift_copy
        self.samples_per_class = self.batch_size // 4
        self.path_img = path_img
        
        # checks
        # provide avail_classes
        self.avail_classes = [*self.image_dict]
        # Data augmentation/processing methods.
        self.transform = transform

        self.reshuffle()


    def reshuffle(self):

        image_dict = copy.deepcopy(self.image_dict) 
        print('shuffling data')
        for sub in image_dict:
            random.shuffle(image_dict[sub])

        total_batches = []
        batch = []
        finished = 0
        if len(image_dict[0]) >= 2*len(image_dict[1]):       # One epoch is finished when all genuine document have been loaded
            while finished == 0:
                if (len(image_dict[0]) >= 2*self.samples_per_class):
                    l_clips = []
                    # Randomly draw 25% of the batch size of fake documents
                    list_fakes_img = list(np.random.choice(image_dict[1],self.samples_per_class))
                    l_clips = l_clips + [(1, x) for x in list_fakes_img]
                
                    # Randomly draw 50% of the batch size of genuine documents
                    list_reals_img = list(image_dict[0][:2*self.samples_per_class])
                    l_clips = l_clips + [(0, x) for x in list_reals_img]
                    image_dict[0] = image_dict[0][2*self.samples_per_class:] 

                    # Randomly draw 25% of the batch size of genuine documents that will be forged on-the-fly. 
                    # Label is set at 2 as "to-be-forged". When the document will be forged the label will be set to 1
                    list_forgery_augm_img = list(np.random.choice(list_reals_img,self.samples_per_class))
                    l_clips = l_clips + [(2, x) for x in list_forgery_augm_img]                
                    batch.append(l_clips)

                if len(batch) == 1:
                    total_batches.append(batch)
                    batch = []
                else:
                    finished = 1
        else:    # for the last batch we randomly draw a set of genuine documents, 
                 # hence it is possible to have duplicate of genuine documents in the last batch
            while finished == 0:
                if (len(image_dict[1]) >= self.samples_per_class):
                    l_clips = []
                    # Randomly draw 50% of the batch size of genuine documents
                    list_reals_img = list(np.random.choice(image_dict[0],2*self.samples_per_class))
                    l_clips = l_clips + [(0, x) for x in list_reals_img]
                
                    # Randomly draw 25% of the batch size of fake documents
                    list_fakes_img = list(image_dict[1][:self.samples_per_class])
                    l_clips = l_clips + [(1, x) for x in list_fakes_img]
                    image_dict[1] = image_dict[1][self.samples_per_class:] 

                    # Randomly draw 25% of the batch size of genuine documents that will be forged on-the-fly. 
                    # Label is set at 2 as "to-be-forged". When the document will be forged the label will be set to 1
                    list_forgery_augm_img = list(np.random.choice(list_reals_img,self.samples_per_class))
                    l_clips = l_clips + [(2, x) for x in list_forgery_augm_img]                
                    batch.append(l_clips)
                
                if len(batch) == 1:
                    total_batches.append(batch)
                    batch = []
                else:
                    finished = 1
        
        random.shuffle(total_batches)
        self.dataset = flatten(flatten(total_batches))

    def __getitem__(self, idx):
        # we use SequentialSampler together with SuperLabelTrainDataset,
        # so idx==0 indicates the start of a new epoch
        # if foregery augmentation is set, document with label 2 will be forged, drawing randomly one of the forgery techniques available: copy paste, crope & replace and inpainting.
        batch_item = self.dataset[idx]   # image path + label
        cls = batch_item[0]              # label
        image = cv2.imread(batch_item[1])        # image
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        if self.faker_data_augmentation:
            if batch_item[0] == 2:
                cls = 1   # change label to one as the document is going to be forged
                image = forgery_augmentation(self.dataset_name, image, self.path_img, batch_item[1], self.shift_copy)

        # perform classic data augmentation on every document
        augmented = self.transform(image=image)
        image = augmented['image']

        return  image, cls   # image array, label


    def __len__(self):
        return len(self.dataset)
