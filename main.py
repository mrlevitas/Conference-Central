#!/usr/bin/env python
import webapp2
from google.appengine.api import app_identity
from google.appengine.api import mail
from conference import ConferenceApi
from models import SpeakerDict
import logging

SPEAKER_IDENTIFIER = 1234

class SetAnnouncementHandler(webapp2.RequestHandler):
    def get(self):
        """Set Announcement in Memcache."""
        # TODO 1
        # use _cacheAnnouncement() to set announcement in Memcache
        ConferenceApi._cacheAnnouncement()

class SendConfirmationEmailHandler(webapp2.RequestHandler):
    def post(self):
        """Send email confirming Conference creation."""
        mail.send_mail(
            'noreply@%s.appspotmail.com' % (
                app_identity.get_application_id()),     # from
            self.request.get('email'),                  # to
            'You created a new Conference!',            # subj
            'Hi, you have created a following '         # body
            'conference:\r\n\r\n%s' % self.request.get(
                'conferenceInfo')
        )

class AddFeaturedSpeaker(webapp2.RequestHandler):
    def post(self):
        """Check Speaker being added in Session & add as featured in memcache if qualifies"""
        speakerName = self.request.get('speakerName')

        dictSpeaker = SpeakerDict.query(SpeakerDict.identifier == SPEAKER_IDENTIFIER).get()

        # no dictionary exists, create one and initialize
        if dictSpeaker is None:
            dictSpeaker = SpeakerDict()
            dictSpeaker.identifier = SPEAKER_IDENTIFIER
            dictSpeaker.put()

        logging.error('BEFORE dictSpeaker is= %s' % dictSpeaker)

        # no dict. entry exists for speaker, initialize to 1
        if dictSpeaker.speaker_num.get(speakerName) == None:
            dictSpeaker.speaker_num[speakerName] = 1
        # increment existing speaker entry by 1 and update memcache w/ new speaker
        else:
            dictSpeaker.speaker_num[speakerName] += 1
            api = ConferenceApi()
            api.cacheFeaturedSpeaker(speakerName)

        logging.error('After dictSpeaker is= %s' % dictSpeaker)
        dictSpeaker.put()




app = webapp2.WSGIApplication([
    ('/crons/set_announcement', SetAnnouncementHandler),
    ('/tasks/send_confirmation_email', SendConfirmationEmailHandler),
    ('/tasks/add_featured_speaker', AddFeaturedSpeaker),
], debug=True)
