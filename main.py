import requests
import xml.etree.ElementTree as ET


def main():
    res = requests.get("https://g1.globo.com/sitemap/g1/2026/04/13_1.xml")
    root = ET.fromstring(res.content)



if __name__ == "__main__":
    main()
