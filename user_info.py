
class User_info():
    def __init__(self, screen_name:str):
        self.screen_name = screen_name
        self.rest_id = None      #用户数字ID
        self.name = None         #用户昵称
        self.statuses_count = None #总推数(含转推)
        self.media_count = None  #含图片视频的推数(不含转推)
        pass
