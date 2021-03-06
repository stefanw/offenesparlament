import sys
import time
import logging
from urlparse import urljoin
from lxml import html
from itertools import count
from pprint import pprint

from webstore.client import URL as WebStore

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.NOTSET)

MEDIATHEK_URL = "http://www.bundestag.de/Mediathek/index.jsp"
MIN_WP = 17
MAX_FAIL = 3
SHORT_URL = "http://dbtg.tv/vid/"

def get_doc(url):
    for i in range(MAX_FAIL):
        try:
            #print url
            doc = html.parse(url)
            if not no_results(doc):
                return doc
        except Exception, e:
            log.exception(e)
        time.sleep(i**2)

def no_results(doc):
    err = doc.find('//p[@class="error"]')
    if err is not None and err.text and 'keine Videos' in err.text:
        return True
    return False

def video_box(doc, prefix):
    area = doc.find('//div[@class="mediathekVideobox"]//div[@class="mediathekVideoText"]')
    vid_elem = area.find('.//li[@class="mp4"]/a')
    pdf_elem = area.find('.//li[@class="pdf"]/a')
    text = html.tostring(area.find('div'))
    text = text.split('<div>', 1)[-1].rsplit('</div>')[0]
    data = {
            prefix + '_context': area.find('h2/span').text.strip(),
            prefix + '_title': area.find('h2/br').tail.strip(),
            prefix + '_text': text,
            prefix + '_mp4_url': urljoin(MEDIATHEK_URL, vid_elem.get('href')) \
                    if vid_elem is not None else None,
            prefix + '_pdf_url': pdf_elem.get('href') if pdf_elem is not None else None,
            prefix + '_source_url': area.find('.//a[@class="kurzUrl"]').get('href')
            }
    return data

def load_sessions(db):
    wp_fails = 0
    for wp in count(MIN_WP):
        wp_fails += 1
        for session in count(1):
            url = SHORT_URL + str(wp) + "/" + str(session)
            doc = get_doc(url)
            if doc is None:
                break
            else:
                wp_fails = 0
                ctx = video_box(doc, 'meeting')
                ctx['meeting_url'] = url
                load_tops(wp, session, ctx, db)
        if wp_fails > MAX_FAIL:
            break

def load_tops(wp, session, context, db):
    for top_id in count(1):
        url = SHORT_URL + str(wp) + "/" + str(session) + "/" + str(top_id)
        doc = get_doc(url)
        if doc is None:
            return
        else:
            log.info("Mediathek, WP %s - Session %s - TOP %s" % (wp, session, top_id))
            top = context.copy()
            top['top_nr'] = top_id
            top.update(video_box(doc, 'top'))
            load_speeches(url, top, db)

def load_speeches(url, context, db):
    Mediathek = db['mediathek']
    for speech_id in count(1):
        url_ = url + "/" + str(speech_id)
        doc = get_doc(url_)
        if doc is None:
            return
        else:
            spch = context.copy()
            spch.update(video_box(doc, 'speech'))
            ps = doc.findall('//div[@class="mediathekPlenarText"]/p')
            if len(ps) > 1:
                spch['speech_meta'] = ps[1].text or '||'
                _, spch['speech_time'], spch['speech_duration'] = \
                        map(lambda s: s.strip(), spch['speech_meta'].split('|'))
                spch['speech_duration'] = spch['speech_duration'].split(": ")[-1]
                spch['speech_time'] = spch['speech_time'].split(" ")[0]
            spch['speech_nr'] = speech_id
            Mediathek.writerow(spch, 
                    unique_columns=['speech_source_url'],
                    bufferlen=None)
            if not 'speech_title' in spch or not spch['speech_title']:
                pprint(spch)
            #name_transform(spch['speech_title'])
    Mediathek.flush()

if __name__ == '__main__':
    assert len(sys.argv)==2, "Need argument: webstore-url!"
    db, _ = WebStore(sys.argv[1])
    print "DESTINATION", db
    load_sessions(db)
