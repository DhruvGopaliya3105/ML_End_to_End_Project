import os 
import sys 
from dataclasses import dataclass 
import pandas as pd 
from sklearn.model_selection import train_test_split 
from src.config import ARTIFACTS_DIR, BASE_DIR
from src.exception import CustomException 
from src.logger import get_logger 
logger = get_logger(__name__) 

@dataclass 
class DataIngestionConfig:
    raw_data_path: str = os.path.join(ARTIFACTS_DIR , "raw.csv") 
    train_data_path: str = os.path.join(ARTIFACTS_DIR , "train.csv")
    test_data_path: str = os.path.join(ARTIFACTS_DIR , "test.csv") 
    source_csv_path: str = os.path.join(BASE_DIR , "notebook" , "data" , "covid_toy.csv") 


class DataIngestion:
    def __init__(self):
        self.ingestion_config = DataIngestionConfig() 

    def initiate_data_ingestion(self):
        logger.info("Data Ingestion started....") 
        try:
            df = pd.read_csv(self.ingestion_config.source_csv_path) 
            logger.info(f"Data read successfullywith shape: {df.shape}") 
            os.makedirs(
                os.path.dirname(self.ingestion_config.raw_data_path),exist_ok=True
            )
            df.to_csv(self.ingestion_config.raw_data_path,index=False, header=True) 
            logger.info("Performing train-test-split") 
            train_set, test_set = train_test_split(
                df , test_size=0.2, random_state=42 , stratify=df['has_covid']
            )
            train_set.to_csv(self.ingestion_config.train_data_path, index=False, header=True) 
            test_set.to_csv(self.ingestion_config.test_data_path, index=False, header=True) 
            logger.info("Data Ingestion completed successfully...")
            logger.info("Jo log online class le rhe h , unko bhi congration , unka bhi data ingestion ho chuka h , leptop per apna hath rkh kr apne aap ko pawan kare.")
            logger.info("----------")
            logger.info("Jinka net nhi chl rha online me , unka bhi data ingestion complete")

            # IMPORTANT: this must be a tuple, not a set.
            #
            # It used to be `return {train_path, test_path}`. A set has no
            # guaranteed order, and Python randomises string hashing on every
            # run, so the caller's `train_path, test_path = ...` unpacking
            # swapped the two files roughly half the time - meaning the model
            # trained on the test split and was scored on the train split.
            return (
                self.ingestion_config.train_data_path,
                self.ingestion_config.test_data_path,
            )
        except Exception as e :
            raise CustomException(e,sys) 

if __name__ == "__main__":
    obj = DataIngestion() 
    obj.initiate_data_ingestion() 
 