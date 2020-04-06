import copy
import re

import lxml
import lxml.etree
import lxml.html


def normalize_text(s: str) -> str:
    s = s.replace("&#13;", "")

    res = ""
    while True:
        m = re.search(r'<a.*?data-cfemail="(.*?)">.*?</a>', s)
        if not m:
            break

        encoded = bytes.fromhex(m.group(1))
        key = encoded[0]
        decoded = "".join([chr(c ^ key) for c in encoded[1:]])

        res += s[:m.start()]
        res += decoded
        s = s[m.end():]

    return res + s


def _inner_html(node: lxml.etree._Element) -> str:
    tmp = lxml.etree.Element('root')
    tmp.text = node.text
    for child in node:
        tmp.append(child)

    res = lxml.html.tostring(tmp, encoding='unicode')

    res = re.sub(r'^<root>', '', res)
    res = re.sub(r'</root>$', '', res)
    res = res.strip()
    
    return res


def inner_html_ru(node: lxml.etree._Element) -> str:
    return _inner_html(node)


def inner_html_xyz(node: lxml.etree._Element) -> str:
    node = copy.deepcopy(node)
    lxml.etree.strip_tags(node, 'a')
    return _inner_html(node)
