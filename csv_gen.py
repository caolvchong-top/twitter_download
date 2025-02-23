import csv
import time
from datetime import datetime

class csv_gen():
    def __init__(self, save_path:str, user_name, screen_name, tweet_range) -> None:
        self.f = open(f'{save_path}/{screen_name}-{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.csv', 'w', encoding='utf-8-sig', newline='')
        self.writer = csv.writer(self.f)

        #初始化
        self.writer.writerow([user_name, screen_name])
        self.writer.writerow(['Tweet Range : ' + tweet_range])
        self.writer.writerow(['Save Path : ' + save_path])
        main_par = ['Tweet Date', 'Display Name', 'User Name', 'Tweet URL', 'Media Type', 'Media URL', 'Saved Filename', 'Tweet Content', 'Favorite Count', 
                    'Retweet Count', 'Reply Count']
        self.writer.writerow(main_par)

        pass

    def csv_close(self):
        self.f.close()

    def stamp2time(self, msecs_stamp:int) -> str:
        timeArray = time.localtime(msecs_stamp/1000)
        otherStyleTime = time.strftime("%Y-%m-%d %H:%M", timeArray)
        return otherStyleTime
    
    def data_input(self, main_par_info:list) -> None:   #数据格式参见 main_par
        main_par_info[0] = self.stamp2time(main_par_info[0])    #传进来的是 int 时间戳, 故转换一下
        self.writer.writerow(main_par_info)

