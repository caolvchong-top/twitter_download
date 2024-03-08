import os
import pickle

class cache_gen():

    def __init__(self, save_path) -> None:
        self.cache_path = save_path + os.sep + "cache_data.log"

        if os.path.exists(self.cache_path):
            with open(self.cache_path, 'rb') as f:
                self.cache_data = pickle.load(f)
        else:
            self.cache_data = set()

    def __del__(self):
        with open(self.cache_path, 'wb') as f:
            pickle.dump(self.cache_data, f)

    def add(self, element):
        self.cache_data.add(element)

    def is_present(self, element):
        if element in self.cache_data:
            return False
        else:
            self.add(element)
            return True


