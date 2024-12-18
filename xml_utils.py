from xml.etree import cElementTree as ElementTree
from xml.etree.ElementTree import ParseError
import tempfile

## --------------------------------------------------------------------------------------------
# https://stackoverflow.com/a/78101353

class XmlListConfig(list):
    def __init__(self, aList):
        for element in aList:
            if element:
                if len(element) == 1 or element[0].tag != element[1].tag:
                    self.append(XmlDictConfig(element))
                elif element[0].tag == element[1].tag:
                    self.append(XmlListConfig(element))
            elif element.text:
                text = element.text.strip()
                if text:
                    self.append(text)

class XmlDictConfig(dict):
    def __init__(self, parent_element):
        if parent_element.items():
            self.update(dict(parent_element.items()))
        for element in parent_element:
            if element:
                if len(element) == 1 or element[0].tag != element[1].tag:
                    aDict = XmlDictConfig(element)
                else:
                    aDict = {element[0].tag: XmlListConfig(element)}
                if element.items():
                    aDict.update(dict(element.items()))
                self.update({element.tag: aDict})
            elif element.items():
                self.update({element.tag: dict(element.items())})
            else:
                self.update({element.tag: element.text})

## --------------------------------------------------------------------------------------------

def write_xml(response):
    outfile_path ="MTD_MSIL2A.xml"
    with open(outfile_path, 'wb') as f:
        f.write(response.content)

def parse_xml():
    tree = ElementTree.parse('MTD_MSIL2A.xml')
    root = tree.getroot()
    xmldict = XmlDictConfig(root)
    return xmldict

def parse_xml_from_response(response):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as temp_file:
        temp_file.write(response.content)
        temp_file_path = temp_file.name

    tree = ElementTree.parse(temp_file_path)
    root = tree.getroot()
    xmldict = XmlDictConfig(root)
    return xmldict