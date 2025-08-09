import os
import httpx
import re
import json
from url_utils import quote_url



##########配置区域##########
cookie = 'auth_token=xxxxxxxxxxx; ct0=xxxxxxxxxxx;'
# 填入 cookie (auth_token与ct0字段) //重要:替换掉其中的x即可, 注意不要删掉分号

user_lst = ['jeleechandayo','matchach','lilmonix3']
# 填入要下载的用户名(@后面的字符),支持多用户下载,在列表里添加即可

##########配置区域##########



_path = 'profile'

_headers = {
    'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    'authorization':'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
}
_headers['cookie'] = cookie
re_token = 'ct0=(.*?);'
_headers['x-csrf-token'] = re.findall(re_token,_headers['cookie'])[0]

def profile_down(screen_name, path):

    url = 'https://twitter.com/i/api/graphql/gEyDv8Fmv2BVTYIAf32nbA/UserByScreenName?variables={"screen_name":"' + screen_name + '","withGrokTranslatedBio":false}&features={"hidden_profile_subscriptions_enabled":true,"payments_enabled":false,"rweb_xchat_enabled":false,"profile_label_improvements_pcf_label_in_post_enabled":true,"rweb_tipjar_consumption_enabled":true,"verified_phone_label_enabled":false,"subscriptions_verification_info_is_identity_verified_enabled":true,"subscriptions_verification_info_verified_since_enabled":true,"highlights_tweets_tab_ui_enabled":true,"responsive_web_twitter_article_notes_tab_enabled":true,"subscriptions_feature_can_gift_premium":true,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"responsive_web_graphql_timeline_navigation_enabled":true}&fieldToggles={"withAuxiliaryUserLabels":true}'
    response = httpx.get(quote_url(url), headers=_headers).text 
    raw_data = json.loads(response)
    try:
        avatar_url = raw_data['data']['user']['result']['avatar']['image_url']
        description = raw_data['data']['user']['result']['legacy']['description']
        if 'profile_banner_url' not in raw_data['data']['user']['result']['legacy']:
            profile_banner_url = None
        else:
            profile_banner_url = raw_data['data']['user']['result']['legacy']['profile_banner_url']

        avatar_url = re.sub(r'_normal(\.\w+)$', r'_400x400\1', avatar_url) 

        avatar_response = httpx.get(avatar_url, headers=_headers)
        profile_banner_response = httpx.get(profile_banner_url, headers=_headers) if profile_banner_url else None

        with open(_path + os.sep + screen_name + '_avatar.jpg', 'wb') as f:
            f.write(avatar_response.content)
        if profile_banner_response:
            with open(_path + os.sep + screen_name + '_banner.jpg', 'wb') as f:
                f.write(profile_banner_response.content)
        with open(_path + os.sep + screen_name + '_description.txt', 'w', encoding='utf-8') as f:
            f.write(description)
    
    except Exception as e:
        print(f'用户: {screen_name}  失败: {e}')
        return True



if __name__ == '__main__':
    if not os.path.exists(_path):
        os.makedirs(_path)
    for user in user_lst:
        _headers['referer'] = 'https://twitter.com/' + user

        print(f'\n正在获取用户: {user}')
        if not profile_down(user, _path):
            print('---------Completed---------')

    print('\nAll tasks completed.')
