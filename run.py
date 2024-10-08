import importlib, os, argparse
from omegaconf import OmegaConf

import lightning.pytorch as pl
from lightning.pytorch.callbacks.early_stopping import EarlyStopping
from lightning.pytorch.callbacks import LearningRateMonitor
from lightning.pytorch.loggers.tensorboard import TensorBoardLogger

import torch
from torch.utils import data
from torchvision import transforms

torch.set_float32_matmul_precision('medium')

def instantiate_from_config(config):
    return get_obj_from_str(config["target"])(**config.get("params", dict()))

def get_obj_from_str(string):
    module, cls = string.rsplit(".", 1)
    return getattr(importlib.import_module(module), cls)

def get_opt():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inference", action="store_true",
                        help="When inferring the model")
    parser.add_argument("--config", type=str, required=True,
                        help="Path of model config file.")
    
    opt = parser.parse_args()
    return opt

def check_opt(opt): 
    return opt

def get_config(opt):
    config = OmegaConf.load(opt.config)
        
    model_config, logger_config, lightning_config, data_config = config.model, config.logger, config.lightning, config.dataset

    return model_config, logger_config, lightning_config, data_config

def transform_init(datasets, transform):
    for dataset in datasets:
        dataset.transform = transform
        
def get_dataloader(data_config, transform=None):
    dataset_list = []
    if "train" in data_config.get_loader:
        train_dataset = instantiate_from_config(data_config.train)
        dataset_list.append(train_dataset)
    if "val" in data_config.get_loader:
        val_dataset = instantiate_from_config(data_config.val)
        dataset_list.append(val_dataset)
    if "test" in data_config.get_loader:
        test_dataset = instantiate_from_config(data_config.test)
        dataset_list.append(test_dataset)
    
    if transform is None:
        transform = transforms.Compose([transforms.ToTensor(),
                                        transforms.Normalize((0.5, ), (0.5, )),
                                        transforms.Resize((data_config.height, data_config.width), antialias=True)])
        
    transform_init(dataset_list, transform)
    
    if data_config.all:
        all_dataset = dataset_list[0]
        for idx, dataset in enumerate(dataset_list):
            if idx > 0:
                all_dataset += dataset
            
        all_loader = data.DataLoader(all_dataset,
                                 batch_size=data_config.batch_size,
                                 num_workers=data_config.num_workers,
                                 drop_last=False)
        
        return all_loader
    
    if "train" in data_config.get_loader:
        train_loader = data.DataLoader(train_dataset, 
                                       batch_size=data_config.batch_size, 
                                       num_workers=data_config.num_workers,
                                       drop_last=True
                                       )
    else:
        train_loader = None
        
    if "val" in data_config.get_loader:
        val_loader = data.DataLoader(val_dataset,
                                     batch_size=data_config.batch_size,
                                     num_workers=data_config.num_workers,
                                     drop_last=True
                                     )
    else:
        val_loader = None
        
    if "test" in data_config.get_loader:
        test_loader = data.DataLoader(test_dataset, 
                                      batch_size=data_config.batch_size, 
                                      num_workers=data_config.num_workers,
                                      drop_last=True
                                      )
    else:
        test_loader = None           
    
    return train_loader, val_loader, test_loader

if __name__ == "__main__":
    opt = get_opt()
    
    model_config, logger_config, lightning_config, data_config = get_config(opt)
    
    model = instantiate_from_config(model_config)
    
    logger = TensorBoardLogger(logger_config.logger_path)
    
    callbacks = []
    if lightning_config.use_earlystop:
        callbacks.append(EarlyStopping(**lightning_config.earlystop_params))
    if lightning_config.use_monitor:
        callbacks.append(LearningRateMonitor(**lightning_config.monitor_params))
    
    trainer = pl.Trainer(logger=logger, callbacks=callbacks,
                            **lightning_config.trainer)
    
    if not opt.inference:
        train_loader, val_loader, test_loader = get_dataloader(data_config)
        
        trainer.fit(model=model,
                    train_dataloaders=train_loader,
                    val_dataloaders=val_loader,
                    ckpt_path=lightning_config.fit.ckpt_path)
        
        if test_loader is not None:
            trainer.test(model=model,
                        dataloaders=test_loader)
        
    else:
        if data_config.all:
            data_loaders = get_dataloader(data_config)
        else:
            _, _, data_loaders = get_dataloader(data_config) # test_loader
        
        trainer.predict(model=model, 
                        dataloaders=data_loaders,
                        ckpt_path=lightning_config.fit.ckpt_path)
        