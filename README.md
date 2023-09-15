# 推特图片下载    ⟵(๑¯◡¯๑) 
推特图片爬虫，以用户名为参数，爬取该用户推文中的图片(默认为**原图**) 

支持排除转推内容 & 多用户爬取 

**目前老马加了API的请求次数限制** 
``` 
Rate limit exceeded 
即表示请求次数已达限制,过会再试吧 
爬完一个用户需要调用的API次数约为:总推数(含转推) / 19 
图片下载不计入次数 
``` 

部署
--- 

**Linux** : 
``` 
git clone https://github.com/caolvchong-top/twitter_download.git 
cd twitter_download 
pip3 install httpx
``` 
**运行** : 
``` 
配置settings.json文件
python3 main.py 
``` 
**Windows** 和上面的一样，配置完setting.json后运行main.py即可 

注意事项
---
**settings.json** 

![20230720140443](https://github.com/caolvchong-top/twitter_download/assets/57820488/c0adb9e0-6039-417d-a271-577740360d1c)


运行截图 
---
![20230720134231](https://github.com/caolvchong-top/twitter_download/assets/57820488/ee6a1c13-2b0c-47e9-a260-1ac529bec678) 

**↑↑图是bug修复前的，仅效果参考**

![20230720134253](https://github.com/caolvchong-top/twitter_download/assets/57820488/6e5ba42f-2dc4-4fa1-8cf6-152246378756)

![20230720135731](https://github.com/caolvchong-top/twitter_download/assets/57820488/8c167bf1-a497-4466-b81c-3f9760ac56e8)

![20230720135833](https://github.com/caolvchong-top/twitter_download/assets/57820488/6361f411-0d46-4371-9de8-425372706077)

