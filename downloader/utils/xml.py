from xml.etree import cElementTree as ElementTree
import logging

logger = logging.getLogger(__name__)

## --------------------------------------------------------------------------------------------
# https://stackoverflow.com/a/78101353

class XmlListConfig(list):
    """
    Converts an XML element containing a list of child elements into a Python list.

    Attributes:
        aList (list): A list of XML elements to be converted.

    Example:
        Given an XML structure:
        <root>
            <item>Value1</item>
            <item>Value2</item>
        </root>

        Parsing `root` with `XmlListConfig(root)` will result in:
        ['Value1', 'Value2']
    """
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
    """
    Converts an XML element and its children into a Python dictionary.

    Attributes:
        parent_element (xml.etree.ElementTree.Element): The XML element to be converted.

    Example:
        Given an XML structure:
        <root>
            <child1>Value1</child1>
            <child2>Value2</child2>
        </root>

        Parsing `root` with `XmlDictConfig(root)` will result in:
        {
            'child1': 'Value1',
            'child2': 'Value2'
        }
    """
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

def parse_manifest(file_path):
    """
    Parses an XML manifest file and converts it into a Python dictionary.

    Args:
        file_path (pathlib.Path): The path to the XML file to be parsed.

    Returns:
        dict: A dictionary representation of the XML structure.

    Example:
        If the XML file contains:
        <manifest>
            <dataObjectSection>
                <dataObject>
                    <byteStream>
                        <fileLocation>
                            <href>./path/to/file</href>
                        </fileLocation>
                    </byteStream>
                </dataObject>
            </dataObjectSection>
        </manifest>

        The function will return a dictionary like:
        {
            'dataObjectSection': {
                'dataObject': [{
                    'byteStream': {
                        'fileLocation': {
                            'href': './path/to/file'
                        }
                    }
                }]
            }
        }
    """
    logger.info(f"Parsing {file_path}...")
    tree = ElementTree.parse(file_path)
    root = tree.getroot()
    xmldict = XmlDictConfig(root)
    return xmldict

def get_files(xmldict):
    """
    Extracts a list of file paths from a parsed XML dictionary.

    Args:
        xmldict (dict): The parsed XML data in dictionary form.

    Returns:
        list: A list of file paths extracted from the XML.

    Example:
        Given the parsed XML structure:
        {
            'dataObjectSection': {
                'dataObject': [{
                    'byteStream': {
                        'fileLocation': {
                            'href': './path/to/file1'
                        }
                    }
                }, {
                    'byteStream': {
                        'fileLocation': {
                            'href': './path/to/file2'
                        }
                    }
                }]
            }
        }

        The function will return:
        ['path/to/file1', 'path/to/file2']
    """
    return [
        file["byteStream"]["fileLocation"]["href"].split("./")[-1]
        for file in xmldict["dataObjectSection"]["dataObject"]
    ]