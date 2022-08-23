import requests
from fake_useragent import UserAgent
import json
import re
import os
from multiprocessing import Pool

def main_download(photo_url:str,user_name,proxies):     #用pool.apply_async传入
    re_rule='media\/(.*?)\?name'
    file_name=re.findall(re_rule,photo_url)[0]
    file_path=user_name+'/'+file_name
    ua=UserAgent()
    headers={
        'user-agent':ua.random
        }
    try:
        response=requests.get(photo_url,headers=headers,proxies=proxies).content
    except Exception as e:
        print(file_name,'下载出错...')
        return
    with open(file_path,'wb') as f:
        f.write(response)
        f.close()
    print(file_name,'===>下载完成')

class Inf_Collection():
    def __init__(self,screen_name:str,cookie=None,proxies=None):
        self.screen_name=screen_name      #用户名，@ 符号后面的那个
        self.ua=UserAgent()
        self.url_1='https://twitter.com/i/api/graphql/gr8Lk09afdgWo7NvzP89iQ/UserByScreenName?variables={"screen_name":"'+self.screen_name+'","withSafetyModeUserFields":true,"withSuperFollowsUserFields":true}'
        self.proxies=proxies
        re_token='ct0=(.*?);'
        csrf_token=re.findall(re_token,cookie)[0]
        self.headers={      #下面这几条都是必要的
            'user-agent':self.ua.random,
            'referer':'https://twitter.com/'+self.screen_name,
            'x-csrf-token':csrf_token,
            #上面这个token很重要，取自cookie里的 ct0 字段，换cookie的时候记得更新
            'authorization':'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
            'cookie':cookie,
            #未登录的用户会有个 x-guest-token (必填，对应的是cookie的gt字段，貌似很快会失效)
            #因为没加对r18信息的判断，所以未登录的情况下一碰到r18推文就立马报错(建议还是用已登录的cookie)
            }
        self.inf_lst=self.get_user_inf()
        self.set_count=self.get_settings()
        self.photo_url=self.photo_search()
        print('\n'+'='*30+'\n图片链接提取完成，开始下载...\n')
        name=re.sub('[<>"|*?/\\:]','',self.inf_lst['name'])        #有的用户名里有特殊字符，要排除
        if not os.path.exists(name):
            os.makedirs(name)
        pool=Pool()
        for i in self.photo_url:
            pool.apply_async(main_download,args=(i,name,proxies,))
        pool.close()
        pool.join()

    def get_user_inf(self):
        inf_lst={}
        response=requests.get(self.url_1,headers=self.headers,proxies=self.proxies).text
        raw_data=json.loads(response)
        inf_lst['id']=raw_data['data']['user']['result']['rest_id']         #用户的数字id
        inf_lst['name']=raw_data['data']['user']['result']['legacy']['name']        #用户的昵称
        inf_lst['statuses_count']=raw_data['data']['user']['result']['legacy']['statuses_count']      #总推数(包括转推)
        inf_lst['media_count']=raw_data['data']['user']['result']['legacy']['media_count']      #总媒体数(大概是图片视频之类的，数字不准确)
        return inf_lst

    def get_settings(self):
        set_count={}
        print('\n昵称：%s\n总推数(包括转推)：%s\n图片数(不准确，仅参考)：%s\n'%(self.inf_lst['name'],self.inf_lst['statuses_count'],self.inf_lst['media_count']))
        is_retweet=input('#一般来说，转推占了总推数的大部分#\n\n爬图片时是否包括转推的内容？(y/n)：').lower()
        if is_retweet=='y':
            set_count['is_retweet']=True
        else:
            set_count['is_retweet']=False
        print('\n\n下载范围只是大概的,像输入130-280,则下载100-300部分\n')
        content_range=input('#下载顺序为,从最新到最早#\n以总推数为参照,请输入下载范围(全部下载则输入 0-总推数 ):')
        content_range=content_range.split('-')
        _start=int(content_range[0])
        _end=int(content_range[1])
        set_count['content_range']=(_start,_end)
        return set_count

    def get_photo_url(self,entries_lst):        #用于提取数据内的图片链接
        all_url_lst=[]
        if self.set_count['is_retweet']:        #包括转推
            for i in entries_lst:
                _url_lst=[]     #提前定义，有的数据两个都不符合
                if 'cursorType' not in i['content']:      #判断是否到底 (看有没有页码信息)
                    if 'itemContent' in i['content'] and 'extended_entities' in i['content']['itemContent']['tweet_results']['result']['legacy']:
                        _url_lst=[
                            x['media_url_https']+'?name=orig'      #默认下载原始大小的(所有格式:small,large,orig)
                            for x in i['content']['itemContent']['tweet_results']['result']['legacy']['extended_entities']['media']
                            if x['type']=='photo'
                            ]
                    elif 'items' in i['content'] and 'clientEventInfo' not in i['content'] and 'extended_entities' in i['content']['items'][0]['item']['itemContent']['tweet_results']['result']['legacy']:
                    #特殊情况，从页面上看是一条推文引用了另一条推文，所以content后面跟的items(列表形式)
                        _url_lst=[
                            x['media_url_https']+'?name=orig'
                            for x in i['content']['items'][0]['item']['itemContent']['tweet_results']['result']['legacy']['extended_entities']['media']
                            if x['type']=='photo'
                            ]
                    all_url_lst+=_url_lst
        else:       #不包括转推
            for i in entries_lst:
                #这部分和上面是一样的，只是加了个转推的判断
                _url_lst=[]
                if 'cursorType' not in i['content']:
                    if 'itemContent' in i['content'] and 'retweeted_status_result' not in i['content']['itemContent']['tweet_results']['result']['legacy'] and 'extended_entities' in i['content']['itemContent']['tweet_results']['result']['legacy']:
                        _url_lst=[
                            x['media_url_https']+'?name=orig'
                            for x in i['content']['itemContent']['tweet_results']['result']['legacy']['extended_entities']['media']
                            if x['type']=='photo'
                            ]
                    elif 'items' in i['content'] and 'clientEventInfo' not in i['content'] and 'retweeted_status_result'not in i['content']['items'][0]['item']['itemContent']['tweet_results']['result']['legacy'] and 'extended_entities' in i['content']['items'][0]['item']['itemContent']['tweet_results']['result']['legacy']:
                        _url_lst=[
                            x['media_url_https']+'?name=orig'
                            for x in i['content']['items'][0]['item']['itemContent']['tweet_results']['result']['legacy']['extended_entities']['media']
                            if x['type']=='photo'
                            ]
                    all_url_lst+=_url_lst
        return all_url_lst
                    

    def photo_search(self):
        _count=0
        bottom_cursor=None        #下一页
        url_top='https://twitter.com/i/api/graphql/_yBYoGGoRdonMeYdEibvyA/UserTweets?variables={"userId":"'+self.inf_lst['id']+'","count":101'
        url_bottom=',"includePromotedContent":false,"withQuickPromoteEligibilityTweetFields":true,"withSuperFollowsUserFields":true,"withDownvotePerspective":false,"withReactionsMetadata":false,"withReactionsPerspective":false,"withSuperFollowsTweetFields":true,"withVoice":true,"withV2Timeline":true}&features={"dont_mention_me_view_api_enabled":true,"interactive_text_enabled":true,"responsive_web_uc_gql_enabled":true,"vibe_api_enabled":true,"responsive_web_edit_tweet_api_enabled":true,"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":false,"responsive_web_enhance_cards_enabled":false}'
        photo_lst=[]
        print('\n开始提取&处理信息...\n\n'+'='*30)
        keep=True
        while keep:
            print('开始处理 %s-%s 条的信息'%(_count,(_count+100)))
            if _count==0:
                _url=url_top+url_bottom
                lst_count=1     #用于instructions里的数据定位
            else:
                _url=url_top+',"cursor":"'+bottom_cursor+'"'+url_bottom
                lst_count=0     #第一页的数据在 lst[1] ,后续所有的数据都在 lst[0]
            
            _keep=True
            while _keep:
                try:
                    response=requests.get(_url,headers=self.headers,proxies=self.proxies)
                    _keep=False
                except Exception as e:
                    print('\n如果你看到这条信息不断的闪烁出现，那说明网络有问题，或是参数输入有误...')
            raw_data=json.loads(response.text)
            entries_lst=raw_data['data']['user']['result']['timeline_v2']['timeline']['instructions'][lst_count]['entries']
            if 'cursorType' in entries_lst[0]['content']:
                keep=False      #第一个就是页码信息,这意味着已经到底了
            elif self.set_count['content_range'][0]-_count<=100:        #到达设定的开始范围，开始提取信息
                print('正在提取该段的图片链接...')
                photo_lst+=self.get_photo_url(entries_lst)
            _count+=100
            bottom_cursor=entries_lst[-1]['content']['value']
            if _count>=self.set_count['content_range'][1]:  #超过设置的结束值，可以停止了
                keep=False

        return photo_lst

#Test
if __name__=='__main__':
    #multiprocessing.freeze_support()       #用pyinstaller打包的时候带上这一行
    screen_name=input('请输入要爬取的用户名(@符号后面的那个):')
    cookie=input('\n请输入cookie:')
    if_proxy=input('\n是否添加代理[机器能直连twitter的就不用(不开VPN)](y/n) :')
    if if_proxy.lower()=='y':
        msg='''\nTip1.使用爬虫代理的，请按照requests_proxies格式输入(字典形式)\n
Tip2.本机开了VPN的，请按照{'https':'127.0.0.1:<port>'}格式输入(把<port>换成VPN代理的端口)\n
请输入代理:'''
        proxies=eval(input(msg))
    else:
        proxies=None
    a=Inf_Collection(screen_name,cookie=cookie,proxies=proxies)
    input('执行完毕，按任意键退出...')




