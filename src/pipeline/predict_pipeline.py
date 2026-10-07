import sys 
import os 
import pandas as pd 
from src.config import ARTIFACTS_DIR
from src.exception import CustomException 
from src.utils import load_object
from src.logger import get_logger 
logger = get_logger(__name__) 

class CustomData:
    def __init__(self, age:int, gender:str , fever:float, cough:str , city:str):
        self.age = age 
        self.gender = gender 
        self.fever = fever 
        self.cough = cough 
        self.city = city 

    def get_data_as_dataframe(self):
        try:
            custom_data_input_dict = {
                "age": [self.age],
                "gender": [self.gender],
                "fever": [self.fever],
                "cough": [self.cough],
                "city": [self.city]
            }
            return pd.DataFrame(custom_data_input_dict)
        except Exception as e :
            raise CustomException(e,sys) 

class PredictPipeline:
    def __init__(self):
        self.model_path = os.path.join(ARTIFACTS_DIR, "model.pkl") 
        self.preprocessor_path = os.path.join(ARTIFACTS_DIR, "preprocessor.pkl") 

    def predict(self, features: pd.DataFrame):
        try:
            logger.info("Loading Model and Preprocessor") 
            model = load_object(self.model_path) 
            preprocessor = load_object(self.preprocessor_path) 

            data_scaled = preprocessor.transform(features) 
            prediction = model.predict(data_scaled) 

            probability = None 
            if hasattr(model, "predict_proba"):
                probability = round(max(model.predict_proba(data_scaled)[0])*100,2)

            result = "Positive" if int(prediction[0]) == 1 else "Negative" 
            logger.info(f"Prediction completed: {result}, confidence_score = {probability}") 
            return result, probability 
        except Exception as e : 
            raise CustomException(e,sys)


def model_available():
    """Check whether the trained model + preprocessor can actually be loaded.

    Returns (True, None) when both files load, or (False, reason) when they do
    not. This matters because scikit-learn pickles are NOT portable between
    scikit-learn versions - a model saved with one version can fail to load
    with another. When that happened, /predict used to quietly fall back to a
    hand-written rule and still show a "Model confidence" figure.
    """

    import os

    for label, path in (
        ("model.pkl", os.path.join(ARTIFACTS_DIR, "model.pkl")),
        ("preprocessor.pkl", os.path.join(ARTIFACTS_DIR, "preprocessor.pkl")),
    ):

        if not os.path.exists(path):

            return False, f"{label} was not found in the artifacts folder."

        try:

            load_object(path)

        except Exception as e:

            return (
                False,
                f"{label} could not be loaded (it was probably saved with a "
                f"different scikit-learn version than the one installed). "
                f"Run:  python train_model.py",
            )

    return True, None
