from __future__ import print_function

import os
import requests
import socket
import time
import datetime
from datetime import date
import json
import oci
import io
#import pytesseract
#import PIL
import logging
import sys

#import httplib2

from flask import Flask, request, Response, abort, jsonify
#from flask_cors import CORS
from PIL import Image

app = Flask(__name__)
#CORS (app)

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

hostname = socket.gethostname()

microtime = lambda: int(round(time.time() * 1000))

os.environ['OMP_THREAD_LIMIT'] = '1'

#config = oci.config.from_file(file_location="../.oci/config")
#compartment_id = config["tenancy"]
#compartment_id = "ocid1.compartment.oc1..aaaaaaaaaphk36ry5vghub24nzdnwuy3chkm4t26mejxf4ah6rufy3fw2ywa"
signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
#object_storage = oci.object_storage.ObjectStorageClient(config)
object_storage = oci.object_storage.ObjectStorageClient({}, signer=signer)
namespace = object_storage.get_namespace().data
try:
    bucket_name = os.environ['BUCKET']
except:
    bucket_name = "clouddemo-public"

object_name = ""
#downloadLink="https://objectstorage.eu-frankfurt-1.oraclecloud.com/n/cloudstarscee/b/clouddemo-public/o/"
downloadLink="https://objectstorage.eu-frankfurt-1.oraclecloud.com/n/" + namespace + "/b/" + bucket_name + "/o/"

def getDownloadLink (namespace, bucket):
    return "https://objectstorage.eu-frankfurt-1.oraclecloud.com/n/" + namespace + "/b/" + bucket + "/o/"

def now ():
    return datetime.datetime.now ().strftime ('%Y-%m-%d %H:%M:%S')

def getfulltext (token):
    response = requests.post ('http://db:8080/db/v1/gettext', json={'token': token}).json ()
    return response['text']

def genwordcloud (token):
    fulltext = getfulltext (token)
    response = requests.post ('http://wc:8080/wordcloud', json={'text': fulltext})
    output = io.BytesIO ()
    output.write (response.content)
    return output

@app.route('/api/v1/list', methods=['GET', 'POST'])
def getlist():
    if request.method == 'POST':
        content=request.get_json()
        try:
            token = content['token']
        except:
            token = ""
    else:
        try:
            token = request.args.get ('token')
        except:
            token = ""

    startmtime = microtime()
    data = requests.post ('http://db:8080/db/v1/list', json={'token': token}).json ()
    endmtime = microtime()
    duration = round ((endmtime - startmtime) / 1000, 3)

    json_data = json.dumps (data, indent=4)

    print (hostname, now (), '/api/v1/list: Token:', token, 'Request duration:', duration, file=sys.stderr)

    return Response (json_data, mimetype='application/json')

@app.route('/api/v1/wordcloud', methods=['GET'])
def getwordcloud():
    token = request.args.get ('token')
    filename = "wordcloud.png"
    try:
        obj = object_storage.list_objects(namespace, bucket_name, prefix=token + '/' + filename)
        data = [dict ({"ID": 1, "url": getDownloadLink (namespace, bucket_name) + token + '/' + filename + "?t=" + str (microtime())})]
    except:
        filename=""
        data = [dict ({"ID": 1, "url": ""})]

    print (hostname, now(), "/api/v1/wordcloud: Token:", token, file=sys.stderr)
    print (hostname, now(), "/api/v1/wordcloud: File:", filename, file=sys.stderr)

    json_data = json.dumps (data)
    return Response (json_data, mimetype='application/json')

@app.route('/api/v1/upload', methods=['POST', 'PUT'])
def upload():
    remote_ip = ""
    user_agent = ""
    if request.environ.get('HTTP_X_FORWARDED_FOR') is None:
        remote_ip = request.environ['REMOTE_ADDR'].split (',')[0]
    else:
        remote_ip = request.environ['HTTP_X_FORWARDED_FOR'].split (',')[0]

    print (hostname, now(), '/api/v1/upload: IP:', remote_ip)

    user_agent = request.headers['User-Agent']

    input_file = io.BytesIO ()

    if request.method == 'PUT':
#Saving image to Object Storage using oci sdk
        fileName = request.args.get ('filename')
        token = request.args.get ('token')

        if len (token) > 0:
            try:
#                obj = object_storage.get_bucket (namespace, token)
                obj = object_storage.get_bucket (namespace, bucket_name)
            except:
#                obj = object_storage.create_bucket (namespace, oci.object_storage.models.CreateBucketDetails(name=token, compartment_id=compartment_id, public_access_type='ObjectReadWithoutList'))
                obj = object_storage.create_bucket (namespace, oci.object_storage.models.CreateBucketDetails(name=bucket_name, compartment_id=compartment_id, public_access_type='ObjectReadWithoutList'))

#            obj = object_storage.put_object(namespace, token, fileName, request.data)
#            endpoint = getDownloadLink (namespace, token) + fileName
            obj = object_storage.put_object(namespace, bucket_name, token +'/' + fileName, request.data)
            endpoint = getDownloadLink (namespace, bucket_name) + token +'/' + fileName
        else:
#            obj = object_storage.put_object(namespace, token, bucket_name, request.data)
#            endpoint = getDownloadLink + (namespace, bucket_name) + fileName
            obj = object_storage.put_object(namespace, bucket_name, token +'/' + fileName, request.data)
            endpoint = getDownloadLink (namespace, bucket_name) + token +'/' + fileName

        input_file.write (request.data)

    else:
#Reading image from Object Storage using oci sdk
        content=request.get_json()
        fileName=content['data']['resourceName']
        token = fileName.split('_')[0]

        obj = object_storage.get_object(namespace, bucket_name, fileName)

        input_file.write (obj.data.content)

    input_image = Image.open (input_file)

    print (hostname, now(), "/api/v1/upload: Token:", token, file=sys.stderr)
    print (hostname, now(), "/api/v1/upload: File:", fileName, file=sys.stderr)


    starttime = now ()
    startmtime = microtime()

    if input_image:
        print (hostname, now(), '/api/v1/upload: Image size:', input_image.width, input_image.height, file=sys.stderr)

#        text = (pytesseract.image_to_string (input_image, config = '--psm 1', lang='eng+rus'))
        response = requests.post ('http://ocr:8080/ocr', json={'filename': token + '/' + fileName, 'bucket': bucket_name, 'token': token}).json()
        text = response['text']
        ocr_hostname = response['hostname']

#    response = requests.post ('http://db:8080/db/v1/gettext', json={'token': token}).json ()
#    return response['text']
#        output = io.BytesIO ()
#        output.write (response.content)

        endtime = now ()
        endmtime = microtime()
        duration = round ((endmtime - startmtime) / 1000, 3)

        print (hostname, now(), '/api/v1/upload: Recognized text:', len (text), 'bytes,', duration, 's.', file=sys.stderr)

        values = {}
        values['hostname'] = ocr_hostname
        values['starttime'] = starttime
        values['endtime'] = endtime
        values['duration'] = duration
        values['text'] = text
        values['filename'] = fileName
        values['token'] = token
        values['link'] = endpoint
        values['ipaddr'] = remote_ip
        values['useragent'] = user_agent

        startmtime = microtime()
        response = requests.post ('http://db:8080/db/v1/insert', json=json.dumps (values))

        endmtime = microtime()
        duration = round ((endmtime - startmtime) / 1000, 3)

        print (hostname, now (), '/api/v1/upload: Database Insert duration:', duration, file=sys.stderr)

        wctime = microtime()
        wcoutput = genwordcloud (token)
        wcfilename = 'wordcloud.png'
#        obj = object_storage.put_object(namespace, token, wcfilename, wcoutput.getvalue ())
        obj = object_storage.put_object(namespace, bucket_name, token + '/' + wcfilename, wcoutput.getvalue ())
        wcoutput.close

        wcduration = round ((microtime () - wctime) / 1000, 6)
        print (hostname, now(), '/api/v1/upload: Wordcloud generation time:', wcduration, 's.', file=sys.stderr)
    else:
        print (hostname, now(), '/api/v1/upload: Error processing image: not an image.', file=sys.stderr)
        return ('Error', 500)

    input_image.close()
    input_file.close()

    return "OK", 200

if __name__ == "__main__":
    app.run(host = '0.0.0.0', port = 8080)