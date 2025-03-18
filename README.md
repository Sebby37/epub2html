# epub2html
Python program that converts an EPUB ebook to a single HTML file! 
By default it'll extract all the epub's resources it can find to a `content` directory, under its UUID. 
You can also instead make it just squish the content into the HTML file as one big happy base64-encoded family! 

Made it because I just kinda felt like it, especially when I learned EPUBs are basically just a collection of HTML files. 
Used as few external libraries as possible, BeautifulSoup is the sole exception because python does NOT have a good HTML parser 
(but it has a pretty decent XML one), and also BeautifulSoup is just so convenient and easy to use!

Tested it on my definetly legally acquired Re:Zero LN EPUBs, converts them all perfectly so far as I can tell!

## Custom Styling
To change the styling of your generated HTML file, simply place an `epub.css` file in the same directory as it! 
You can use the `.epub-container` selector to change what you need I guess, otherwise break a leg with every other selector you want. 
A sample one that I use is included in the repo, convenient!

## Usage
```
usage: epub2html [-h] [-s] filename

Tool to convert an EPUB file into a single HTMl document, extracting its
resources along the way.

positional arguments:
  filename           Filename (or directory) of the EPUB(s) to convert.

options:
  -h, --help         show this help message and exit
  -s, --single-file  Whether to squish all the resources into a single HTML
                     file. (Optional)
```
