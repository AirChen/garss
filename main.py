import feedparser
import time
import os
import re
import pytz
from datetime import datetime
import yagmail
import requests
from jinja2 import FileSystemLoader, Environment
import json
import copy
from urllib import parse, request
from qiniu import Auth, put_file, etag
import qiniu.config

header_info = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.116 Safari/537.36"}

def get_rss_info(feed_url):
    result = {"result": []}
    # 如何请求出错,则重新请求,最多五次
    for i in range(5):
        try:            
            # 设置15秒钟超时
            feed_url_content = requests.get(feed_url,  timeout= 15 ,headers = header_info).content
            feed = feedparser.parse(feed_url_content)
            feed_entries = feed["entries"]
            feed_entries_length = len(feed_entries)
            print("==feed_url=>>", feed_url, "==len=>>", feed_entries_length)
            for entrie in feed_entries[0: feed_entries_length-1]:
                title = entrie["title"]
                link = entrie["link"]
                result["result"].append({
                    "title": title,
                    "link": link
                })
            break
        except Exception as e:
            print(feed_url+"第+"+str(i)+"+次请求出错==>>",e)
            pass

    return result["result"]

def send_mail(email, title, contents):
    # 判断secret.json是否存在
    user = ""
    password = ""
    host = ""
    try:
        if(os.environ["USER"]):
            user = os.environ["USER"]
        if(os.environ["PASSWORD"]):
            password = os.environ["PASSWORD"]
        if(os.environ["HOST"]):
            host = os.environ["HOST"]
    except:
        print("无法获取github的secrets配置信息,开始使用本地变量")
        if(os.path.exists(os.path.join(os.getcwd(),"secret.json"))):
            with open(os.path.join(os.getcwd(),"secret.json"),'r') as load_f:
                load_dict = json.load(load_f)
                user = load_dict["user"]
                password = load_dict["password"]
                host = load_dict["host"]
                # print(load_dict)
        else:
            print("无法获取发件人信息")
            return
    
    # 连接邮箱服务器    
    yag = yagmail.SMTP(user = user, password = password, host=host)
    # 发送邮件
    yag.send(email, title, contents)

def process_line(line):
    # 获取link
    link = re.findall(r'\[订阅地址\]\((.*)\)', line)[0]
    # 生成超链接
    rss_info = get_rss_info(link)
    latest_content = "[暂无法通过爬虫获取信息](https://github.com/AirChen/garss)"    

    if(len(rss_info) > 0):
        rss_info[0]["title"] = rss_info[0]["title"].replace("|", "\|")
        rss_info[0]["title"] = rss_info[0]["title"].replace("[", "\[")
        rss_info[0]["title"] = rss_info[0]["title"].replace("]", "\]")
        latest_content = "[" + "‣ " + rss_info[0]["title"] +"](" + rss_info[0]["link"] +")"        

    if(len(rss_info) > 1):
        rss_info[1]["title"] = rss_info[1]["title"].replace("|", "\|")
        rss_info[1]["title"] = rss_info[1]["title"].replace("[", "\[")
        rss_info[1]["title"] = rss_info[1]["title"].replace("]", "\]")
        latest_content = latest_content + "<br/>[" + "‣ " +  rss_info[1]["title"] +"](" + rss_info[1]["link"] +")"        

    # 生成after_info
    after_info = line.replace("{{latest_content}}", latest_content)
    print("====latest_content==>", latest_content)
    
    return after_info, copy.copy(rss_info)
 
def replace_readme():
    new_edit_readme_md = ""
    session_list = []

    global g_rss_datetime
    global g_rss_num
    # 读取EditREADME.md
    with open(os.path.join(os.getcwd(),"EditREADME.md"),'r') as load_f:
        edit_readme_lines = load_f.readlines()
        session = {}
        session['list'] = []
        g_rss_num = 0
        for line in edit_readme_lines:
            if re.match(r'.*\[订阅地址\]\(.*\).*\{\{latest_content\}\}.*', line) != None:
                new_line, entity_list = process_line(line)                
                session['list'] += entity_list[:5]
                g_rss_num += 1
            elif re.match(r'.*\<h2 id\=\".*\"\>.*\<\/h2\>.*', line) != None:
                if g_rss_num != 0:
                    session_list.append(session)
                    session = {}
                    session['list'] = []
                
                t = re.findall(r'\<h2 id\=\"(.*)\"\>(.*)\<\/h2\>', line)[0][0]
                session['title'] = t                
                new_line = line
            elif re.match(r'.*\{\{ga_rss_datetime\}\}.*', line) != None:                
                # 填充统计时间
                g_rss_datetime = datetime.fromtimestamp(int(time.time()),pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
                new_line = line.replace("{{ga_rss_datetime}}", str(g_rss_datetime))
            else:
                new_line = line

            new_edit_readme_md = new_edit_readme_md + new_line
        if len(session['list']) > 0:
            session_list.append(session)
        new_edit_readme_md = new_edit_readme_md.replace("{{rss_num}}", str(g_rss_num))

    # 将新内容
    with open(os.path.join(os.getcwd(),"README.md"),'w') as load_f:
        load_f.write(new_edit_readme_md)
    
    return session_list

def get_email_list():
    email_list = []
    with open(os.path.join(os.getcwd(),"tasks.json"),'r') as load_f:
        load_dic = json.load(load_f)
        for task in load_dic["tasks"]:
            email_list.append(task["email"])
    return email_list

def get_bing_img():
    BING_API = "https://cn.bing.com/HPImageArchive.aspx?format=js&idx=0&n=10&nc=1612409408851&pid=hp&FORM=BEHPTB&uhd=1&uhdwidth=3840&uhdheight=2160"
    BING_URL = "https://cn.bing.com"
    
    req = request.Request(url=BING_API, headers=header_info)
    res = request.urlopen(req)
    res = res.read()

    json_obj = json.loads(res) 
    # res_data = str(res.decode(encoding='utf-8')) 转码utf-8后

    url_params = json_obj['images'][0]['url']
    url_img = BING_URL + url_params.split('&')[0]

    copy_right = json_obj['images'][0]['copyright']
    copy_right = copy_right.split(' ')[0]    

    return url_img, copy_right

def save_img(url, name):
    req = request.Request(url, headers=header_info)
    response = request.urlopen(req)
    filename = "./img.jpg"
    if (response.getcode() == 200):
        with open(filename, "wb") as f:
            f.write(response.read())

        # 七牛
        access_key = ""
        secret_key = ""
        try:
            if(os.environ["ACCESS_KEY"]):
                access_key = os.environ["ACCESS_KEY"]
            if(os.environ["SECRET_KEY"]):
                secret_key = os.environ["SECRET_KEY"]            
        except:
            print("无法获取github的secrets配置信息,开始使用本地变量")
            if(os.path.exists(os.path.join(os.getcwd(),"secret.json"))):
                with open(os.path.join(os.getcwd(),"secret.json"),'r') as load_f:
                    load_dict = json.load(load_f)
                    access_key = load_dict["access_key"]
                    secret_key = load_dict["secret_key"]                    
            else:
                print("无法上传图片至七牛云")
                return
        
        #构建鉴权对象
        q = Auth(access_key, secret_key)
        #要上传的空间
        bucket_name = 'bingcollection'
        #上传后保存的文件名
        key = name + '.jpg'
        #生成上传 Token，可以指定过期时间等
        token = q.upload_token(bucket_name, key, 3600)
        #要上传文件的本地路径    
        put_file(token, key, filename)

def main():
    session_list = replace_readme()
    bing_img, img_name = get_bing_img()

    env = Environment(loader=FileSystemLoader('./templates'))
    template = env.get_template('basic.html')
    cout_html = template.render(web_title="RSS订阅", 
                rss_num=g_rss_num, ga_rss_datetime=g_rss_datetime,
                back_img=bing_img,
                session_list=session_list)

    with open(os.path.join(os.getcwd(),"render.html"),'w') as load_f:
        load_f.write(cout_html)

    save_img(bing_img, img_name)

    email_list = get_email_list()
    send_mail(email_list, "RSS订阅", cout_html)

main()