import requests
from bs4 import BeautifulSoup
import re

def test_fetch():
    url = "https://guba.eastmoney.com/list,zssh000001,f_1.html"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://guba.eastmoney.com/"
    }
    
    response = requests.get(url, headers=headers, timeout=10)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find all a tags matching post details
    a_tags = soup.find_all('a', href=re.compile(r'/news,|caifuhao\.eastmoney\.com/news/'))
    
    if a_tags:
        a = a_tags[0]
        # Let's get the <tr> row element
        tr = a.parent.parent.parent
        print(f"TR Tag: {tr.name}, class: {tr.get('class')}")
        print("\nTR COMPLETE HTML:")
        print(tr.prettify())
        
        print("\nCOLUMNS (TDs) INSIDE THE ROW:")
        for idx, td in enumerate(tr.find_all('td', recursive=False)):
            print(f"Column {idx+1}: class={td.get('class')} text='{td.text.strip()}' HTML='{str(td).strip()}'")
            
    else:
        print("No post link tags found.")

if __name__ == "__main__":
    test_fetch()
