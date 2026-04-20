import subprocess  # 用于运行main.py文件
import json  # 用于读取和写入json文件
import os

# 定义一个函数来修改settings.json文件
def modify_settings(save_path, user_lst):
    # 读取settings.json文件，并将其转换为字典settings
    with open('settings.json', 'r', encoding='UTF-8') as file:
        settings = json.load(file)

    # 修改settings.json文件中的"save_path"和"user_lst"
    settings['save_path'] = save_path
    settings['user_lst'] = user_lst

    # 写入settings.json文件，确保中文字符不被转义
    with open('settings.json', 'w', encoding='UTF-8') as file:
        json.dump(settings, file, indent=4, ensure_ascii=False)



def main():
    # 定义路径和用户列表的字典
    # "就算是windows路径也请用 '/' ,而不是反斜杠(可以留空)"
    # "填入要下载的用户名(@后面的字符),支持多用户下载,用户名字间逗号(英文逗号,不要有空格)隔开"
    path_user_dict = {
        'F:/推特下载路径/涩涩画师': "1",
        'F:/推特下载路径/正常画师': "2",
        'F:/推特下载路径/1': "3",
        'F:/推特下载路径/2': "4,5,6",
    }

    # 遍历字典中的每个路径和用户列表，
    # path_user_dict.items输出的是一个元组，第一个元素是路径，第二个元素是用户列表
    for save_path, user_lst in path_user_dict.items():
        # 修改settings.json文件,
        modify_settings(save_path, user_lst)

        # 运行main.py文件
        subprocess.run(['python', 'main.py'])


if __name__ == '__main__':
    main()
