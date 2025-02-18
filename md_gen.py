import time
from datetime import datetime

class md_gen():
    def __init__(self, save_path:str, user_name, screen_name, tweet_range) -> None:
        self.f = open(f'{save_path}/{screen_name}-{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.md', 'w', encoding='utf-8-sig', newline='')
        self.f.write(f"{user_name} {screen_name}\n")
        self.f.write(f"Tweet Range: {tweet_range}\n")
        self.f.write(f"Save Path: {save_path}\n\n")

    def md_close(self):
        self.f.close()

    def stamp2time(self, msecs_stamp:int) -> str:
        timeArray = time.localtime(msecs_stamp/1000)
        otherStyleTime = time.strftime("%Y-%m-%d %H:%M", timeArray)
        return otherStyleTime
    
    def data_input(self, content) -> None:
        self.f.write(content + '\n')
