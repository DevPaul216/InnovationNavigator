import os

# Define color scheme
COLOR_BLOCKED = "rgb(250, 240, 220)"
COLOR_COMPLETED = "rgb(104, 223, 200)"
COLOR_IN_PROGRESS = "rgb(255, 165, 0)"

# Define data store path
DATA_STORE_PATH = os.path.join("stores", "data_stores")

# Define view assignment dictionary
VIEW_ASSIGNMENT_DICT = {
    "general": None,  # This will be set by the main module
    "Start": None,
    "End": None,
    "Prompts": None
}

# Define special templates
SPECIAL_TEMPLATES = [
    "align", "discover", "define", "develop", "deliver", "continue",
    "empathize", "define+", "ideate", "prototype", "test"
] 