# 推特图片下载    ⟵(๑¯◡¯๑) 
推特图片爬虫，以用户名为参数，爬取该用户推文中的图片(默认为**原图**) 

支持排除转推内容 & 下载指定区间内容 

部署
--- 

**Linux** : 
``` 
git clone https://github.com/caolvchong-top/twitter_download.git 
cd twitter_download 
pip3 install requirements.txt 
``` 
**运行** : 

`python3 start.py` 

**Windows** 可以在release里拿打包好的版本 

注意事项
---

![QQ图片20220823151206](https://user-images.githubusercontent.com/57820488/186094395-c715fbdd-7297-43e1-bd07-11090823fb63.png)  

**代理格式**  
1.  
`{'https':'代理地址'}`

2.本机开了VPN的请按下面这个格式填  
`{'https':'127.0.0.1:<port>'}`  

例：  
`{'https':'127.0.0.1:8888'}`  

**尽量不要一次性下载太多，可能会被封IP**

运行截图 
---
![QQ图片20220823152042](https://user-images.githubusercontent.com/57820488/186098262-428a3693-4b3b-46f7-b732-7031d0aa6cef.png)

![QQ图片20220823152759](https://user-images.githubusercontent.com/57820488/186098291-1ac763c0-bc37-40e2-8d2d-e0f38d8703de.png)

![QQ图片20220823152919](https://user-images.githubusercontent.com/57820488/186098305-dd0db6fb-7094-4399-9dd0-7f9ed65bddb7.png)

