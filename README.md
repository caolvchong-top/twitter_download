# 推特图片下载    ⟵(๑¯◡¯๑) 
推特 图片 & 视频 下载，以用户名为参数，爬取该用户推文中的图片与视频(含gif)

支持排除转推内容 & 多用户爬取 & 时间范围限制 & 按Tag获取 & 纯文本获取 

---
**目前老马加了API的请求次数限制** 
``` 
当程序抛出：Rate limit exceeded 
即表示该账号当日的API调用次数已耗尽

if 选择包含转推:
  爬完一个用户需要调用的API次数约为:总推数(含转推) / 19
elif 不包含:
  会大大减少API调用次数

下载不计入次数 
```

# Change Log 
* **2024-05-11**
  * 支持获取纯文本推文--**请直接配置text_down.py文件并运行**（临时功能）
    
    // (下方有预览) 注意，此功能会大量消耗API次数(参考上方公式)，默认排除转推内容
* **2024-05-10**
  * 支持按Tag获取--**请直接配置tag_down.py文件并运行**（临时功能）
  
    // 保存格式 (下方有预览)：. / {#Tag} / {datetime} \_ {@username} \_ { md5( media_url )[:4] } . { png / mp4 }

* **2024-03-09**
  * 支持记录已下载内容,避免重复下载 (如有问题请发issue)
  * 支持自动同步最新内容
* **2024-01-16**
  * 适配 [ **喜欢(Likes)** ] 标签页 
* **2024-01-10**
  * 新增统计数据 [ **Favorite, Retweet, Reply** ]
* **2024-01-05**
  * 适配Twieer新标签页 [ **亮点(HighLights)** ]
* **2023-12-12**
  * 适配Twitter新API
* **2023-10-12**
  * 添加 生成爬取信息 功能
* **2023-10-06**
  * 添加 时间范围限制 功能
  * 统一文件保存格式
    * 文件夹：用户id (@后面的)
    * 文件：推文日期-[img/vid]_下载计数.文件后缀
      
* **2023-09-15**
  * 添加 视频下载 功能
 
---

| ![e53923662b627a645fcd2b0b3feadb3b](https://github.com/caolvchong-top/twitter_download/assets/57820488/39da9658-f40f-40d6-8480-9dff850076da) |
|:--:| 
| **(๑´ڡ`๑)** | 


部署
--- 

**Linux** : 
``` 
git clone https://github.com/caolvchong-top/twitter_download.git 
cd twitter_download 
pip3 install httpx==0.23.0
#非0.23版本可能会出现不知名问题
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

![settings](https://github.com/caolvchong-top/twitter_download/assets/57820488/9cb4ac26-4e3a-4953-9dfd-8e3d85046b2d)


效果预览
---
![20230720134231](https://github.com/caolvchong-top/twitter_download/assets/57820488/ee6a1c13-2b0c-47e9-a260-1ac529bec678) 


**↑↑图是bug修复前的，仅效果参考**



![20230720134253](https://github.com/caolvchong-top/twitter_download/assets/57820488/6e5ba42f-2dc4-4fa1-8cf6-152246378756)

![20230720135731](https://github.com/caolvchong-top/twitter_download/assets/57820488/8c167bf1-a497-4466-b81c-3f9760ac56e8)
 
**按Tag获取(仅媒体文件)** 

![image](https://github.com/caolvchong-top/twitter_download/assets/57820488/aa109e18-5ef1-4d77-902c-658ed1b3ff53)

**纯文本推文获取(仅文本)** 

![QQ截图20240511032859](https://github.com/caolvchong-top/twitter_download/assets/57820488/0998b6b1-c313-4b1d-a78e-525a666098b2)



**图片下载效果**

![test1](https://github.com/caolvchong-top/twitter_download/assets/57820488/736f7554-612b-4bec-8baf-4a5ab45c6e04)


**视频下载效果**

![test2](https://github.com/caolvchong-top/twitter_download/assets/57820488/6f732042-6f96-4e7a-bd16-e7d08a46a90e)



**生成的CSV统计**

![屏幕截图 2023-10-12 223755](https://github.com/caolvchong-top/twitter_download/assets/57820488/b5dfc741-e10f-409a-b298-d56ea236bc5f)



