#!/usr/bin/env python

"""
conference.py -- Udacity conference server-side Python App Engine API;
    uses Google Cloud Endpoints

$Id: conference.py,v 1.25 2014/05/24 23:42:19 wesc Exp wesc $

created by wesc on 2014 apr 21

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'

from datetime import datetime
import json
import os
import time

import logging
import endpoints
from protorpc import messages
from protorpc import message_types
from protorpc import remote

from google.appengine.api import urlfetch
from google.appengine.ext import ndb
from google.appengine.api import memcache
from google.appengine.api import taskqueue

from models import Profile
from models import ProfileMiniForm
from models import ProfileForm
from models import TeeShirtSize
from models import Conference
from models import ConferenceForm
from models import ConferenceForms
from models import ConferenceQueryForm
from models import ConferenceQueryForms
from models import BooleanMessage
from models import ConflictException
from models import StringMessage
from models import Session
from models import SessionForm
from models import SessionForms


from settings import WEB_CLIENT_ID

from utils import getUserId

EMAIL_SCOPE = endpoints.EMAIL_SCOPE
API_EXPLORER_CLIENT_ID = endpoints.API_EXPLORER_CLIENT_ID

MEMCACHE_ANNOUNCEMENTS_KEY = "RECENT ANNOUNCEMENTS"
MEMCACHE_SPEAKER_KEY = "FEATURED SPEAKER"

CONF_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
)

CONF_POST_REQUEST = endpoints.ResourceContainer(
    ConferenceForm,
    websafeConferenceKey=messages.StringField(1),
)

SESS_GET_REQUEST_BY_TYPE = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
    sessType=messages.StringField(2),
)

SESS_GET_REQUEST_BY_SPEAKER = endpoints.ResourceContainer(
    message_types.VoidMessage,
    speaker=messages.StringField(1),
)

SESS_GET_REQUEST_MAX_DURATION = endpoints.ResourceContainer(
    message_types.VoidMessage,
    maxDuration=messages.IntegerField(1),
)

SESS_GET_REQUEST_TIME = endpoints.ResourceContainer(
    message_types.VoidMessage,
    timeSTR=messages.StringField(1),
)

ADD_WISHLIST_POST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    sess_key=messages.StringField(1),
)

RETURN_FEATURED_SPEAKER = endpoints.ResourceContainer(
    message_types.VoidMessage,
    speaker=messages.StringField(1),
)

DEFAULTS = {
    "city": "Default City",
    "maxAttendees": 0,
    "seatsAvailable": 0,
    "topics": ["Default", "Topic"],
}

OPERATORS = {
            'EQ':   '=',
            'GT':   '>',
            'GTEQ': '>=',
            'LT':   '<',
            'LTEQ': '<=',
            'NE':   '!='
            }

FIELDS = {
            'CITY': 'city',
            'TOPIC': 'topics',
            'MONTH': 'month',
            'MAX_ATTENDEES': 'maxAttendees',
            }

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

@endpoints.api(name='conference',
               version='v1',
               allowed_client_ids=[WEB_CLIENT_ID, API_EXPLORER_CLIENT_ID],
               scopes=[EMAIL_SCOPE])
class ConferenceApi(remote.Service):
    """Conference API v0.1"""

# - - - Sessions - - - - - - -  - - - - - - - - - - - - - - - - -

    @endpoints.method(SessionForm, SessionForm, path='session',
                      http_method='POST', name='createSession')
    def createSession(self, request):
        """Create new Session endpoint."""
        return self._createSessionObject(request)

    def _createSessionObject(self, request):
        """Create Session object, returning SessionForm/request."""
        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        conf = ndb.Key(urlsafe=request.confwebsafeKey).get()
        organizerId = conf.organizerUserId

        # session creation open only to the organizer of the conference
        if user_id != organizerId:
            raise endpoints.UnauthorizedException('User not Organizer of Conference, Cannot create Sessions')

        # session must have a name
        if not request.sessionName:
            raise endpoints.BadRequestException("Session 'name' field required")

        # session must have a speaker
        if not request.speaker:
            raise endpoints.BadRequestException("Session 'speaker' field required")

        # getFeauturedSpeaker implementation as Task
        speakerName = request.speaker
        taskqueue.add(params={'speakerName': speakerName},
                      url='/tasks/add_featured_speaker')

        # copy SessionForm/ProtoRPC Message into dictionary
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}
        del data['confwebsafeKey']

        # convert date from strings to Date objects
        if data['Date']:
            data['Date'] = datetime.strptime(data['Date'][:10], "%Y-%m-%d").date()

        # convert time from strings to time object
        if data['startTime']:
            data['startTime'] = datetime.strptime(data['startTime'][:10], "%H:%M").time()

        # create Conference key from websafe url key string
        c_key = ndb.Key(Conference, request.confwebsafeKey)
        # allocate new Session ID with Conference key as parent
        s_id = Session.allocate_ids(size=1, parent=c_key)[0]
        # make Session key from ID
        s_key = ndb.Key(Session, s_id, parent=c_key)
        data['key'] = s_key

        # create Session object in datastore
        Session(**data).put()

        # return (modified) SessionForm
        return request

    """
    getConferenceSessions(websafeConferenceKey)
        Given a conference, return all sessions
    """
    @endpoints.method(CONF_GET_REQUEST, SessionForms,
                      path='conference/{websafeConferenceKey}/allsessions',
                      http_method='GET', name='getConferenceSessions')
    def getConferenceSessions(self, request):
        """Return requested sessions of Conference (by websafeConferenceKey)."""
        # get Conference object from request; bail if not found
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)

        # make Conference key
        c_key = ndb.Key(Conference, request.websafeConferenceKey)
        # create ancestor query for this conference
        sessionsAll = Session.query(ancestor=c_key)
        # return SessionForms
        return SessionForms(items=[self._copySessionToForm(sess) \
                            for sess in sessionsAll])

    def _copySessionToForm(self, sess):
        """Copy relevant fields from Session to SessionForm."""
        sf = SessionForm()
        for field in sf.all_fields():
            if hasattr(sess, field.name):
                # convert Date to date string; just copy others
                if field.name.endswith('Date'):
                    setattr(sf, field.name, str(getattr(sess, field.name)))
                elif field.name.endswith('Time'):
                    setattr(sf, field.name, str(getattr(sess, field.name)))
                else:
                    setattr(sf, field.name, getattr(sess, field.name))
            elif field.name == "confwebsafeKey":
                setattr(sf, field.name, sess.key.urlsafe())
        sf.check_initialized()
        return sf

    """
    getConferenceSessionsByType(websafeConferenceKey, typeOfSession)
        Given a conference, return all sessions of a specified type
        (eg lecture, keynote, workshop)
    """
    @endpoints.method(SESS_GET_REQUEST_BY_TYPE, SessionForms,
                      path='conference/{websafeConferenceKey}/sessionsbyType',
                      http_method='GET', name='getConferenceSessionsByType')
    def getConferenceSessionsByType(self, request):
        # check if conference exists
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)

        # make Conference key
        c_key = ndb.Key(Conference, request.websafeConferenceKey)
        # create ancestor query for this conference
        sessionsAll = Session.query(ancestor=c_key)
        sessionsType = sessionsAll.filter(Session.typeOfSession == request.sessType)
        # return SessionForms
        return SessionForms(items=[self._copySessionToForm(sess) \
                            for sess in sessionsType])

    """
    getSessionsBySpeaker(speaker)
        Given a speaker, return all sessions given by this particular speaker,
        across all conferences
    """
    @endpoints.method(SESS_GET_REQUEST_BY_SPEAKER, SessionForms,
                      path='sessionsbySpeaker',
                      http_method='GET', name='getConferenceSessionsBySpeaker')
    def getConferenceSessionsBySpeaker(self, request):
        sessionsAll = Session.query()
        sessionsSpeaker = sessionsAll.filter(Session.speaker == request.speaker)
        # return SessionForms
        return SessionForms(items=[self._copySessionToForm(sess) \
                            for sess in sessionsSpeaker])

    """
    sessionMaxDuration(maximumDuration)
        Given a maximum duration in minutes for a session, return all Sessions
        across all conferences that satisfy this time restraint
    """
    @endpoints.method(SESS_GET_REQUEST_MAX_DURATION, SessionForms,
                      path='sessionsMaxDuration',
                      http_method='GET', name='sessionMaxDuration')
    def sessionMaxDuration(self, request):
        sessionsAll = Session.query()
        sessionsLT = sessionsAll.filter(Session.duration <= request.maxDuration)
        # return SessionForms
        return SessionForms(items=[self._copySessionToForm(sess) \
                            for sess in sessionsLT])

    """
    sessionsbyTime(startTime)
        Given a specific start time in the form of HH:mm in 24 hour format,
        return all Sessions across all conferences which start at that time
    """
    @endpoints.method(SESS_GET_REQUEST_TIME, SessionForms,
                      path='sessionsByTime',
                      http_method='GET', name='sessionsbyTime')
    def sessionsbyTime(self, request):
        # convert time from strings to time object
        timeObj = datetime.strptime(request.timeSTR, "%H:%M").time()
        sessionsAll = Session.query()
        sessionsTime = sessionsAll.filter(Session.startTime == timeObj)
        # return SessionForms
        return SessionForms(items=[self._copySessionToForm(sess) \
                            for sess in sessionsTime])

# - - - Wishlists - - - -  - - - - - - - - - - - - - - - - -
# https://discussions.udacity.com/t/what-is-getfeaturedspeaker-method-supposed-to-do/18768/3

    """
    addSessionToWishlist(SessionKey)
        adds the session to the user's list of sessions they are interested in
        attending
    """
    # wishlist is open to all conferences.
    @endpoints.method(ADD_WISHLIST_POST, BooleanMessage,
                      path='addSessionToWishlist',
                      http_method='POST', name='addSessionToWishlist')
    def addSessionToWishlist(self, request):
        sess = ndb.Key(urlsafe=request.sess_key).get()

        # check that session exists
        if not sess:
            raise endpoints.NotFoundException(
                'No session found with key: %s' % request.sess_key)
        # get user Profile
        prof = self._getProfileFromUser()
        # add session key to user's profile in sessionWishlistKeys
        prof.sessionWishlistKeys.append(request.sess_key)
        prof.put()

        return BooleanMessage(data=True)

    """
    getSessionsInWishlist()
        query for all the sessions that the user is interested in
    """
    @endpoints.method(message_types.VoidMessage, SessionForms,
                      path='getSessionWishlist',
                      http_method='GET', name='getSessionsInWishlist')
    def getSessionsInWishlist(self, request):
        # get user profile
        prof = self._getProfileFromUser()

        # get keys for all sessions in wishlist
        sess_keys = [ndb.Key(urlsafe=sessId) for sessId in prof.sessionWishlistKeys]
        # fetch sessions from datastore.
        # Using get_multi(array_of_keys) to fetch all keys at once.
        # not fetching them one by one!
        sessionsWL = ndb.get_multi(sess_keys)
        return SessionForms(items=[self._copySessionToForm(sess) \
                            for sess in sessionsWL])

# - - - Featured Speaker - - - - - - - - - - - - - - - - - -

    def cacheFeaturedSpeaker(self, speakerName):
        """Create featured Speaker & assign to memcache; used by
        createSession.
        """
        if speakerName:
            memcache.set(MEMCACHE_SPEAKER_KEY, speakerName)
        else:
            # If there are no feat. speakers
            # delete the memcache entry
            memcache.delete(MEMCACHE_SPEAKER_KEY)

    @endpoints.method(CONF_GET_REQUEST, StringMessage,
                      path='getFeaturedSpeaker',
                      http_method='GET', name='getFeaturedSpeaker')
    def getFeaturedSpeaker(self, request):
        """Return featured Speaker from memcache"""

        # return an existing speaker from Memcache
        featuredSpeaker = memcache.get(MEMCACHE_SPEAKER_KEY)

        return StringMessage(data=featuredSpeaker)


# - - - Conference objects - - - - - - - - - - - - - - - - -

    def _copyConferenceToForm(self, conf, displayName):
        """Copy relevant fields from Conference to ConferenceForm."""
        cf = ConferenceForm()
        for field in cf.all_fields():
            if hasattr(conf, field.name):
                # convert Date to date string; just copy others
                if field.name.endswith('Date'):
                    setattr(cf, field.name, str(getattr(conf, field.name)))
                else:
                    setattr(cf, field.name, getattr(conf, field.name))
            elif field.name == "websafeKey":
                setattr(cf, field.name, conf.key.urlsafe())
        if displayName:
            setattr(cf, 'organizerDisplayName', displayName)
        cf.check_initialized()
        return cf

    def _createConferenceObject(self, request):
        """Create or update Conference object, returning ConferenceForm/request."""
        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        if not request.name:
            raise endpoints.BadRequestException("Conference 'name' field required")

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}
        del data['websafeKey']
        del data['organizerDisplayName']

        # add default values for those missing (both data model & outbound Message)
        for df in DEFAULTS:
            if data[df] in (None, []):
                data[df] = DEFAULTS[df]
                setattr(request, df, DEFAULTS[df])

        # convert dates from strings to Date objects; set month based on start_date
        if data['startDate']:
            data['startDate'] = datetime.strptime(data['startDate'][:10], "%Y-%m-%d").date()
            data['month'] = data['startDate'].month
        else:
            data['month'] = 0
        if data['endDate']:
            data['endDate'] = datetime.strptime(data['endDate'][:10], "%Y-%m-%d").date()

        # set seatsAvailable to be same as maxAttendees on creation
        # both for data model & outbound Message
        if data["maxAttendees"] > 0:
            data["seatsAvailable"] = data["maxAttendees"]
            setattr(request, "seatsAvailable", data["maxAttendees"])

        # make Profile Key from user ID
        p_key = ndb.Key(Profile, user_id)
        # allocate new Conference ID with Profile key as parent
        c_id = Conference.allocate_ids(size=1, parent=p_key)[0]
        # make Conference key from ID
        c_key = ndb.Key(Conference, c_id, parent=p_key)
        data['key'] = c_key
        data['organizerUserId'] = request.organizerUserId = user_id

        # create Conference & return (modified) ConferenceForm
        Conference(**data).put()
        # send email to organizer confirming conference creation
        taskqueue.add(params={'email': user.email(),
                      'conferenceInfo': repr(request)},
                      url='/tasks/send_confirmation_email')

        return request

    @endpoints.method(ConferenceForm, ConferenceForm, path='conference',
                      http_method='POST', name='createConference')
    def createConference(self, request):
        """Create new conference."""
        return self._createConferenceObject(request)

    @endpoints.method(CONF_GET_REQUEST, ConferenceForm,
                      path='conference/{websafeConferenceKey}',
                      http_method='GET', name='getConference')
    def getConference(self, request):
        """Return requested conference (by websafeConferenceKey)."""
        # get Conference object from request; bail if not found
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)
        prof = conf.key.parent().get()
        # return ConferenceForm
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

# - - - Registration - - - - - - - - - - - - - - - - - - - -

    @ndb.transactional(xg=True)
    def _conferenceRegistration(self, request, reg=True):
        """Register or unregister user for selected conference."""
        retval = None
        # get user Profile
        prof = self._getProfileFromUser()

        # check if conf exists given websafeConfKey
        wsck = request.websafeConferenceKey
        conf = ndb.Key(urlsafe=wsck).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # register
        if reg:
            # check if user already registered otherwise add
            if wsck in prof.conferenceKeysToAttend:
                raise ConflictException(
                    "You have already registered for this conference")

            # check if seats avail
            if conf.seatsAvailable <= 0:
                raise ConflictException(
                    "There are no seats available.")

            # register user, take away one seat
            prof.conferenceKeysToAttend.append(wsck)
            conf.seatsAvailable -= 1
            retval = True

        # unregister
        else:
            # check if user already registered
            if wsck in prof.conferenceKeysToAttend:

                # unregister user, add back one seat
                prof.conferenceKeysToAttend.remove(wsck)
                conf.seatsAvailable += 1
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        prof.put()
        conf.put()
        return BooleanMessage(data=retval)

    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
                      path='conference/{websafeConferenceKey}',
                      http_method='POST', name='registerForConference')
    def registerForConference(self, request):
        """Register user for selected conference."""
        return self._conferenceRegistration(request)

    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
                      path='conference/{websafeConferenceKey}',
                      http_method='DELETE', name='unregisterFromConference')
    def unregisterFromConference(self, request):
        """Unregister user for selected conference."""
        return self._conferenceRegistration(request, reg=False)

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='conferences/attending',
                      http_method='GET', name='getConferencesToAttend')
    def getConferencesToAttend(self, request):
        """Get list of conferences that user has registered for."""
        # get user profile
        prof = self._getProfileFromUser()

        # get conferenceKeysToAttend from profile
        conf_keys = [ndb.Key(urlsafe=wsck) for wsck in prof.conferenceKeysToAttend]
        # fetch conferences from datastore.
        # Use get_multi(array_of_keys) to fetch all keys at once.
        # Do not fetch them one by one!
        conferences = ndb.get_multi(conf_keys)

        # return set of ConferenceForm objects per Conference
        return ConferenceForms(items=[self._copyConferenceToForm(conf, "") \
                               for conf in conferences])

# - - - Profile objects - - - - - - - - - - - - - - - - - - -

    def _copyProfileToForm(self, prof):
        """Copy relevant fields from Profile to ProfileForm."""
        # copy relevant fields from Profile to ProfileForm
        pf = ProfileForm()
        for field in pf.all_fields():
            if hasattr(prof, field.name):
                # convert t-shirt string to Enum; just copy others
                if field.name == 'teeShirtSize':
                    setattr(pf, field.name, getattr(TeeShirtSize, getattr(prof, field.name)))
                else:
                    setattr(pf, field.name, getattr(prof, field.name))
        pf.check_initialized()
        return pf

    def _getProfileFromUser(self):
        """Return user Profile from datastore, creating new one if non-existent."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # get Profile from datastore
        user_id = getUserId(user)
        p_key = ndb.Key(Profile, user_id)

        # get the entity from datastore by using get() on the key
        profile = p_key.get()

        # create a new Profile from logged in user data
        if not profile:
            profile = Profile(
                userId=None,
                key=p_key,
                displayName=user.nickname(),
                mainEmail=user.email(),
                teeShirtSize=str(TeeShirtSize.NOT_SPECIFIED),
            )
            profile.put()

        return profile

    def _doProfile(self, save_request=None):
        """Get user Profile and return to user, possibly updating it first."""
        # get user Profile
        prof = self._getProfileFromUser()

        # if saveProfile(), process user-modifyable fields
        if save_request:
            for field in ('displayName', 'teeShirtSize'):
                if hasattr(save_request, field):
                    val = getattr(save_request, field)
                    if val:
                        setattr(prof, field, str(val))
            # TODO 4
            # put the modified profile to datastore
            prof.put()
        # return ProfileForm
        return self._copyProfileToForm(prof)

    @endpoints.method(message_types.VoidMessage, ProfileForm,
                      path='profile', http_method='GET', name='getProfile')
    def getProfile(self, request):
        """Return user profile."""
        return self._doProfile()

    @endpoints.method(ProfileMiniForm, ProfileForm,
                      path='profile', http_method='POST', name='saveProfile')
    def saveProfile(self, request):
        """Update & return user profile."""
        return self._doProfile(request)

# - - - Queries - - - - - - - - - - - - - - - - - - -

    def _getQuery(self, request):
        """Return formatted query from the submitted filters."""
        q = Conference.query()
        inequality_filter, filters = self._formatFilters(request.filters)

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Conference.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Conference.name)

        for filtr in filters:
            if filtr["field"] in ["month", "maxAttendees"]:
                filtr["value"] = int(filtr["value"])
            formatted_query = ndb.query.FilterNode(filtr["field"], filtr["operator"], filtr["value"])
            q = q.filter(formatted_query)
        return q

    def _formatFilters(self, filters):
        """Parse, check validity and format user supplied filters."""
        formatted_filters = []
        inequality_field = None

        for f in filters:
            filtr = {field.name: getattr(f, field.name) for field in f.all_fields()}

            try:
                filtr["field"] = FIELDS[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException("Filter contains invalid field or operator.")

            # Every operation except "=" is an inequality
            if filtr["operator"] != "=":
                # check if inequality operation has been used in previous filters
                # disallow the filter if inequality was performed on a different field before
                # track the field on which the inequality operation is performed
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException("Inequality filter is allowed on only one field.")
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters)

    @endpoints.method(ConferenceQueryForms, ConferenceForms,
                      path='queryConferences',
                      http_method='POST',
                      name='queryConferences')
    def queryConferences(self, request):
        """Query for conferences."""
        conferences = self._getQuery(request)

        # return individual ConferenceForm object per Conference
        return ConferenceForms(items=[self._copyConferenceToForm(conf, "") \
                               for conf in conferences])

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='getConferencesCreated',
                      http_method='POST', name='getConferencesCreated')
    def getConferencesCreated(self, request):
        """Return conferences created by user."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # make profile key
        p_key = ndb.Key(Profile, getUserId(user))
        # create ancestor query for this user
        conferences = Conference.query(ancestor=p_key)
        # get the user profile and display name
        prof = p_key.get()
        displayName = getattr(prof, 'displayName')
        # return set of ConferenceForm objects per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, displayName) for conf in conferences])

# - - - Announcements - - - - - - - - - - - - - - - - - - - -

    @staticmethod
    def _cacheAnnouncement():
        """Create Announcement & assign to memcache; used by
        memcache cron job & putAnnouncement().
        """
        confs = Conference.query(ndb.AND(
            Conference.seatsAvailable <= 5,
            Conference.seatsAvailable > 0)
        ).fetch(projection=[Conference.name])

        if confs:
            # If there are almost sold out conferences,
            # format announcement and set it in memcache
            announcement = '%s %s' % (
                'Last chance to attend! The following conferences '
                'are nearly sold out:',
                ', '.join(conf.name for conf in confs))
            memcache.set(MEMCACHE_ANNOUNCEMENTS_KEY, announcement)
        else:
            # If there are no sold out conferences,
            # delete the memcache announcements entry
            announcement = ""
            memcache.delete(MEMCACHE_ANNOUNCEMENTS_KEY)

        return announcement

    @endpoints.method(message_types.VoidMessage, StringMessage,
                      path='conference/announcement/get',
                      http_method='GET', name='getAnnouncement')
    def getAnnouncement(self, request):
        """Return Announcement from memcache."""
        # return an existing announcement from Memcache or an empty string.
        announcement = memcache.get(MEMCACHE_ANNOUNCEMENTS_KEY)
        if not announcement:
            announcement = ""
        return StringMessage(data=announcement)

# registers API
api = endpoints.api_server([ConferenceApi])
