import requests
import os
import binascii
import struct
import argparse
import sys
import shutil
from PIL import Image, ImageDraw, ImageFont
from urlparse import urlparse
import numpy as np
import scipy
import scipy.misc
import scipy.cluster

NUM_CLUSTERS = 5

CLIENT_ID = ""
CLIENT_SECRET = ""


def get_access_token(client_id, client_secret):
    """
    Get the access token from Spotify
    """
    body_params = {'grant_type': "client_credentials"}
    url = 'https://accounts.spotify.com/api/token'

    response = requests.post(url, data=body_params, auth=(client_id, client_secret))
    if response.status_code == 200:
        return response.json()['access_token']
    else:
        sys.exit("Failed to get access token. Is your client_id and client_secret correct?")


def get_api_url(url):
    """
    Get the api url from the song link or the Spotify URI

    Example:
    - https://open.spotify.com/track/7H9sqtNVPp6eoxnJRMUmm4?si=jtQGu_1MQGOF-2WscCvbnA
    - spotify:track:7H9sqtNVPp6eoxnJRMUmm4
    """
    parsed_url = urlparse(url)

    type = None
    spotify_id = None

    if parsed_url.scheme == 'http' or parsed_url.scheme == 'https':
        type = parsed_url.path.split('/')[1]
        spotify_id = parsed_url.path.split('/')[2]
    elif parsed_url.scheme == 'spotify':
        type = parsed_url.path.split(':')[0]
        spotify_id = parsed_url.path.split(':')[1]
    else:
        sys.exit("Failed to build api url.")

    return "https://api.spotify.com/v1/%ss/%s" % (type, spotify_id)  # add an 's' after the type

def spotify_download_playlist(url, headers, directory):
    url = get_api_url(url)
    response = requests.get(url, headers=headers).json()
    create_csv(directory)
    for item in response["tracks"]["items"]:
        spotify_get_images(item['track'], directory)
        write_to_csv(item['track'], directory)


def create_csv(directory):
    shutil.copy("TagWriter_MassEncoding_template_eng.csv", os.path.join(directory, "playlist.csv"))

def write_to_csv(trackdata, directory):
    with open(os.path.join(directory, "playlist.csv"), "a") as myfile:
        myfile.write("URL,%s,URI,%s - %s,,,\n" % (trackdata['uri'], trackdata['artists'][0]['name'], trackdata['name']))


def spotify_code_url(format, size, bgcolor, textcolor, uri):
    """
    url = https://scannables.scdn.co/uri/plain/[format]/[background-color-in-hex]/[code-color-in-text]/[size]/[spotify-URI]
    """
    return "https://scannables.scdn.co/uri/plain/%s/%s/%s/%s/%s" % (format, bgcolor, textcolor, str(size), uri)


def spotify_cover_downloader(url, headers, directory):
    """
    Download an album cover from Spotify
    """
    url = get_api_url(url)

    response = requests.get(url, headers=headers).json()

    spotify_get_images(response, directory)

def spotify_get_images(trackdata, directory):

    cover_url = trackdata['album']['images'][0]['url']
    cover_name = trackdata['id'] + '_cover.jpeg'
    if directory:
        cover_name = os.path.join(directory, cover_name)

    img_data = requests.get(cover_url).content
    with open(cover_name, 'wb') as handler:
        handler.write(img_data)
        print "Your cover was saved! (%s)" % cover_name

    im = Image.open(cover_name)
    im = im.resize((150, 150))      # optional, to reduce time
    ar = np.asarray(im)
    shape = ar.shape
    ar = ar.reshape(scipy.product(shape[:2]), shape[2]).astype(float)

    # print('finding clusters')
    codes, dist = scipy.cluster.vq.kmeans(ar, NUM_CLUSTERS)
    # print('cluster centres:\n', codes)

    vecs, dist = scipy.cluster.vq.vq(ar, codes)         # assign codes
    counts, bins = scipy.histogram(vecs, len(codes))    # count occurrences

    index_max = scipy.argmax(counts)                    # find most frequent
    peak = codes[index_max]
    colour = binascii.hexlify(bytearray(int(c) for c in peak)).decode('ascii')
    print('most frequent is %s (#%s)' % (str(peak), colour))
    luminance = ( 0.299 * peak[0] + 0.587 * peak[1] + 0.114 * peak[2])/255
    if luminance > 0.5:
        text = "black"
    else:
        text = "white"
    code_url = spotify_code_url("png", 640, colour, text, trackdata['uri'])
    print(code_url)
    code_data = requests.get(code_url).content
    code_name = trackdata['id'] + '_code.png'
    if directory:
        code_name = os.path.join(directory, code_name)
    with open(code_name, 'wb') as handler:
        handler.write(code_data)
        print "Your code was saved! (%s)" % code_name
    
    images = [Image.open(x) for x in [cover_name, code_name]]
    widths, heights = zip(*(i.size for i in images))

    width = max(widths)
    height = int(width*7/5)
    fillheight = height - sum(heights) 

    new_im = Image.new('RGB', (width, height))
   
    y_offset = 0
    new_im.paste(images[0], (0,0))
    # new_im.paste(text_img, (0,images[0].size[1]))
    new_im.paste(images[1], (0,height-images[1].size[1]))
    
    draw = ImageDraw.Draw(new_im)

    song_font = ImageFont.truetype('Roboto-Bold.ttf', size=40)
    artist_font = ImageFont.truetype('Roboto-Regular.ttf', size=30)
    draw.rectangle([(0,images[0].size[1]),(width, fillheight + images[0].size[1])], 
        fill='#' + colour)
    draw.text((40,20 + images[0].size[1]), trackdata['artists'][0]['name'], fill=text, font=artist_font)
    draw.text((40,60 + images[0].size[1]), trackdata['name'], fill=text, font=song_font)

    full_name = trackdata['id'] + '_full.png'
    if directory:
        full_name = os.path.join(directory, full_name)
    
    new_im.save(full_name)
    
    


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Download album cover from Spotify.')
    parser.add_argument("url", help="Song or playlist url")
    parser.add_argument("--directory", help="download directory")
    parser.add_argument("--client_id", help="Spotify client_id")
    parser.add_argument("--client_secret", help="Spotify client_secret")

    args = parser.parse_args()

    if args.client_id and args.client_secret:
        client_id = args.client_id
        client_secret = args.client_secret
    else:
        client_id = os.environ.get("SPOTIFY_CLIENT_ID", CLIENT_ID)
        client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", CLIENT_SECRET)

    headers = {"Authorization": "Bearer %s" % get_access_token(client_id, client_secret)}

    if "playlist" in args.url:
        spotify_download_playlist(args.url, headers, args.directory)
    else:
        spotify_cover_downloader(args.url, headers, args.directory)
