import os
import base64
import shutil
import argparse
import posixpath
from zipfile import ZipFile
from dataclasses import dataclass
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

@dataclass
class BookInfo:
    title: str          # Book title
    identifier: str     # Book UUID
    rootfile_path: str  # Path to the rootfile (content.opf)
    path: str           # Root path of the epub (rootfile's path)
    namespace: str      # The stupid XML namespace

@dataclass
class Resource:
    id: str             # Internal resource ID
    href: str           # Link to the resource
    filename: str       # Just the filename
    media_type: str     # The mimetype (think text/css sorta stuff)

@dataclass
class Book:
    content: BookInfo
    resources: dict[str, Resource] # Key is filename
    spine: dict[str, Resource] # Key is ID

# Utility func because XML files are a pain in the ass to work with
def get_namespace(tag_name: str) -> str:
    return tag_name[:tag_name.index("}") + 1]

# Takes the epub zip and returns a(n ordered) dictionary of the format seen in the function
# The order is that of which they are ordered in the spine section
def build_book_info(epub: ZipFile) -> Book:
    """Notes
    - The TOC is something I also need to parse
    - The spine has the toc="ncx", which is an ID set in <manifest> that references the toc.ncx file
    - The toc.ncx file has a <navmap> collection which is of the format:
        <navPoint id="{IDK UNIQUE I GUESS}" playOrder="1" class="chapter">
        <navLabel>
            <text>{CHAPTER NAME}</text>
        </navLabel>
        <content src="{THE FIRST PAGE OF THAT CHAPTER, NOT ID BUT FILENAME}"/>
        </navPoint>
    """
    
    book_info = Book(BookInfo("", "", "", "", ""), dict(), dict())
    
    # Load the container file
    with epub.open("META-INF/container.xml") as container_file:
        container = container_file.read().decode()
        container = ET.fromstring(container)
        container_ns = get_namespace(container.tag)
    
    # Figure out the path of the content file
    content_path = container.find(container_ns + "rootfiles")
    content_path = content_path.find(container_ns + "rootfile")
    content_path = content_path.get("full-path")
    book_info.content.rootfile_path = content_path
    book_info.content.path = os.path.dirname(content_path)
    
    # Load the content file
    with epub.open(content_path) as content_file:
        content = content_file.read().decode()
        content = ET.fromstring(content)
        content_ns = get_namespace(content.tag)
        book_info.content.namespace = content_ns
    
    # Build the dictionary from the spine
    spine = content.find(content_ns + "spine")
    for itemref in spine:
        book_info.spine[itemref.attrib["idref"]] = None
    
    # Populate the spine entries from the manifest
    # Also get the resources from the book (such as the images)
    manifest = content.find(content_ns + "manifest")
    for item in manifest:
        filename = os.path.basename(item.attrib["href"])
        
        # The spine
        if item.attrib["id"] in book_info.spine:
            book_info.spine[item.attrib["id"]] = Resource(
                item.attrib["id"],
                item.attrib["href"],
                filename,
                item.attrib["media-type"]#.split("/")[0]
            )
        # The resources (not xmls though, those are gonna be parsed and such)
        else:
            if "xml" not in item.attrib["media-type"]:
                book_info.resources[filename] = Resource(
                    item.attrib["id"],
                    item.attrib["href"],
                    filename,
                    item.attrib["media-type"]#.split("/")[0]
                )
    
    # Find some of the book's extra info from manifests I can't seem to access
    for metadata in content.find(content_ns + "metadata"):
        if "title" in metadata.tag:
            book_info.content.title = metadata.text
        elif "identifier" in metadata.tag and "id" in metadata.attrib:
            book_info.content.identifier = metadata.text
    
    return book_info

# Sets up the directories and such needed for the final extract
# Also stores all the images and such there too
def extract_resources(epub: ZipFile, book_info: Book):
    # First all the proper needed ones
    if not os.path.exists("content"):
        os.mkdir("content")
    
    book_dir = os.path.join("content", book_info.content.identifier)
    if not os.path.exists(book_dir):
        os.mkdir(book_dir)
    
    # Now extract the media time!
    for resource in book_info.resources.values():
        mimetype = resource.media_type.split("/")[0]
        
        # Make resource dir if we need to
        resource_dir = os.path.join(book_dir, mimetype)
        if not os.path.exists(resource_dir):
            os.mkdir(resource_dir)
        
        # Extract da resource
        # Can't use ZipFile.extract, as it keeps the files directory stucture which we DO NOT want :)
        extract_path = os.path.join(resource_dir, resource.filename)
        resolved_path = posixpath.normpath(os.path.join(book_info.content.path, resource.href))
        with epub.open(resolved_path) as resource_zip, open(extract_path, "wb") as resource_extract:
            shutil.copyfileobj(resource_zip, resource_extract)

# Takes a resource and generates a base64 data URI, like seriously didn't you read the method name???
def generate_b64_uri(epub: ZipFile, book_info: Book, resource: Resource) -> str:
    with epub.open(os.path.join(book_info.content.path, resource.href)) as file:
        resource_bytes = base64.b64encode(file.read())
    return "data:" + resource.media_type + ";base64," + resource_bytes.decode()

# Stitches the book together based on the spine
# Bassicly splices the (x)html files into one and corrects all resource links
# More specifically, for resources like css and jpeg it needs to correct them to their new links in the resources dir
# For links to xHTML files, however, it needs to instead jump to the point in the full doc where that starts
def stitch_book_together(epub: ZipFile, book_info: Book, single_file: bool = False):
    resources_dir = os.path.join("content", book_info.content.identifier)
    full_html = BeautifulSoup('<html><head><link href="epub.css" rel="stylesheet" type="text/css"/></head><body><div class="epub-container"></div></body></html>', 'lxml')
    
    for i, id in enumerate(book_info.spine):
        with epub.open(os.path.join(book_info.content.path, book_info.spine[id].href)) as doc:
            html = BeautifulSoup(doc.read(), "html.parser")
            
            # Oh boy, fixing links time Q_Q
            for tag in html.find_all(["link", "img", "image", "a"]): # No scripts because they're causing me a pain by not having their .js files indexed
                # Get the name of the link attribute
                # This stupid looping is because apparently xlink:href exists, and it's used for the cover of all things
                ref_attr = None
                for attr in tag.attrs:
                    if "href" in attr:
                        ref_attr = attr
                    elif "src" in attr:
                        ref_attr = attr
                if not ref_attr:
                    continue
                
                # Ignore actual links lol
                link = tag[ref_attr]
                filename = os.path.basename(link)
                if "://" in link:
                    continue
                
                # Remove links to (x)htmls and instead just jump to their locations and such
                if ".html" in link or ".xhtml" in link:
                    if "#" in link:
                        tag[ref_attr] = link[link.index("#"):]
                    else:
                        tag[ref_attr] = "#" + filename
                # Otherwise correct the path
                else:
                    file_info = book_info.resources[filename]
                    if not single_file:
                        fixed_path = os.path.join(resources_dir, file_info.media_type.split("/")[0], filename)
                    else:
                        fixed_path = generate_b64_uri(epub, book_info, file_info)
                    tag[ref_attr] = fixed_path
            
            # Append any new tags to the full head
            if i > 0 and i < len(book_info.spine) - 1:
                for tag in html.head.findChildren(recursive=False):
                    if tag not in full_html.head:
                        full_html.head.append(tag)
            
            # Append the body contents now
            body_div = html.new_tag("div", id=book_info.spine[id].filename)
            for tag in html.body.findChildren(recursive=False):
                body_div.append(tag)
            body_div.append(html.new_tag("br"))
            full_html.body.div.append(body_div)
    
    # Finally, time to clean up stupid fake characters that break the look of pages â€
    full_html = str(full_html)
    full_html = full_html.replace("“", "&ldquo;")
    full_html = full_html.replace('”', "&rdquo;")
    full_html = full_html.replace('‘', "&lsquo;")
    full_html = full_html.replace('’', "&rsquo;")
    full_html = full_html.replace('–', "&ndash;")
    full_html = full_html.replace('—', "&mdash;")
    full_html = full_html.replace('…', "&hellip;")
    
    return full_html

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="epub2html",
        description="Tool to convert an EPUB file into a single HTMl document, extracting its resources along the way."
    )
    
    parser.add_argument("filename", type=str, help="Filename (or directory) of the EPUB(s) to convert.")
    parser.add_argument("-s", "--single-file", action="store_true", help="Whether to squish all the resources into a single HTML file. (Optional)")
    
    return parser.parse_args()

# Big time!
def convert_epub(filename: str, single_file: bool) -> None:
    # Meat and several potatoes
    print("Beginning conversion of", filename)
    with ZipFile(filename) as epub:
        book_info = build_book_info(epub)
        print("  Processed book info")
        
        if not single_file:
            extract_resources(epub, book_info)
            print("  Extracted book's resources with identifier of", book_info.content.identifier)
        
        book_str = stitch_book_together(epub, book_info, single_file)
        print("  Generated HTML")
    
    # Donezo
    with open(book_info.content.title + ".html", "w+") as outfile:
        outfile.write(book_str)
        print("  Done conversion! Written HTML to", outfile.name)

def main() -> None:
    # Arguing
    args = parse_args()
    
    # Conversion time!!!!!
    if os.path.isfile(args.filename):
        convert_epub(args.filename, args.single_file)
        
    elif os.path.isdir(args.filename):
        for file in os.listdir(args.filename):
            file = os.path.join(args.filename, file)
            if not os.path.isfile(file) or not file.endswith(".epub"):
                continue
            
            convert_epub(file, args.single_file)
    else:
        print("Invalid file :(")
        exit(1)

if __name__ == "__main__":
    main()
