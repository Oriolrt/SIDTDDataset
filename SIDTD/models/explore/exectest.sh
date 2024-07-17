# Train EfficientNet model
#CUDA_VISIBLE_DEVICES=0 python test.py --name='EfficientNet_faker_data_augmentation' --dataset='clip_cropped_MIDV2020' --model='efficientnet-b3' --type_split kfold --nsplits 1 --static no --pretrained no

# Train Trans FG model
#CUDA_VISIBLE_DEVICES=0 python test.py --name='trans_fg_faker_data_augmentation' --dataset='clip_cropped_MIDV2020' --model='trans_fg' --type_split kfold --nsplits 1 --static no --pretrained no

#CUDA_VISIBLE_DEVICES=0 python test.py --name='coatten_fcn_model_faker_data_augmentation' --dataset='clip_cropped_MIDV2020' --model='coatten_fcn_model' --type_split kfold --nsplits 1 --static no --pretrained no

CUDA_VISIBLE_DEVICES=1 python test.py --name='coatten_fcn_model' --type_split kfold --nsplits 1 --static='yes' --pretrained no --type_data templates  --dataset='SIDTD' --model='coatten_fcn_model' --batchSize 128

#CUDA_VISIBLE_DEVICES=1 python test.py --name='coatten_fcn_model' --type_split kfold --nsplits 10 --static='yes' --pretrained no --type_data clips_cropped  --dataset='clip_cropped_SIDTD' --model='coatten_fcn_model' --batchSize 128