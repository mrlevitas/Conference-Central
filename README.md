6/29/2015
code written by: Roman Levitas, Wesley Chun of Google, & Udacity team
contact: mrlevitas@yahoo.com

Directions given:
https://docs.google.com/document/d/1H9anIDV4QCPttiQEwpGe6MnMBx92XCOlz0B4ciD7lOs/pub

app id:
scalable-apps-example

Deployed version of Conference Central can be accessed here:
https://scalable-apps-example.appspot.com

                     CONFERENCE CENTRAL
***************************Summary**********************************
This zip contains all necessary files & foldersto run the fully functional 
Conference Central web application using the Google App Engine to host & scale 
with incoming users.
Besides the front end functionality of the web app, multiple endpoints have been
implemented to expand the functionality of the application.
User authentication via Google+ is also implemented for users to personalize 
their experience by registering for conferences, etc.

The files and folders are:
1) conference.py
2) models.py
3) settings.py
4) utils.py
5) main.py
6) app.yaml
7) cron.yaml
8) index.yaml
9)  ./templates
10) ./static

***************************General Usage****************************
An installation of Python 2.7 is required to run the web application.

To run the Conference Central Web App project:

1. Download [Google App Engine (GAE) for your OS with the Python SDK][1].
   
2. Run GAE Launcher and go to 'File'->'Add Existing Application'. Choose the 
   directory where you have unzipped all the above mentioned files & folders.

3. Select the 'scalable-apps-example' project and hit 'Run'. Click 'Logs' and 
   see which port to use to locally run the web app. Something like the 
   following should appear:
   "Starting admin server at: http://localhost:8002"

4. Open a webbrowser and navigate to http://localhost:xxxx 
   where xxxx is your designated port from the logs.

*******************************files & folders*******************************

1) conference.py
################################################################################
This is the main file of the application which contains all of the API endpoints
used for the backend of the Conference Central UI as well as some more endpoints
which can be accessed via:
localhost:xxxx/_ah/api/explorer
where xxxx is the port to your local admin server.

These endpoints extend the functionality of Conference Central to include
sessions and are assigned in tasks 1 & 3 (more on task 2 below). 
Sessions can have speakers, start time, duration, type of session (workshop, 
lecture etc.), highlights, etc. (the etc. is specified in the models.py file)
The endpoints associated with Sessions are listed below:

--------------------------------------------------------------------------------
Task 1: 
Basic Session functionality within a conference as well as 2 queries


createSession(SessionForm, websafeConferenceKey) 
   -- open only to the organizer of the conference, Session created as child of
      conference

getConferenceSessions(websafeConferenceKey) 
   -- Given a conference, return all sessions
      Uses helper method  _copySessionToForm(Session) to copy ndb Session object
      to protoRPC form for transmission

getConferenceSessionsByType(websafeConferenceKey, typeOfSession) 
   -- Given a conference, return all sessions of a specified type 
      (eg lecture, keynote, workshop)

getSessionsBySpeaker(speaker) 
   -- Given a speaker, return all sessions given by this particular speaker, 
      across all conferences
--------------------------------------------------------------------------------
Task 3: 
2 Additional Session queries & Query problem

sessionMaxDuration(maximumDuration)
   -- Given a maximum duration in minutes for a session, return all Sessions
      across all conferences that satisfy this time restraint

sessionsbyTime(startTime)
   -- Given a specific start time in the form of HH:mm using 24 hour format, 
      return all Sessions across all conferences which start at that time



"Solve the following query related problem

Let’s say that you don't like workshops and you don't like sessions after 7 pm.
How would you handle a query for all non-workshop sessions before 7 pm? 
What is the problem for implementing this query? 
What ways to solve it did you think of?"

The != (not-equal) operations are implemented by combining inequality filters 
using the OR operation. 

!= value
is implemented as

(property < value) OR (property > value)

and then the session after 7pm would be another inequality filter on a different
property than topics, specifically time.

Directly from the GAE docs: 
"Note: As mentioned earlier, the Datastore rejects queries using inequality 
filtering on more than one property."

So the problem with implementing this query is using inequality filtering on two
different properties.

A way around this dilemma would be to use equality filters (==) and combine it
with OR() to search for other topics in a conference. If we want to avoid 
workshops, we can set equality to all remaining topics (ie. topic == lecture)
and combine all available topics using OR ie. 
OR(topic == lecture, topic == seminar, etc)
--------------------------------------------------------------------------------

Task 2: 
adding/retrieving Sessions to/from Wishlist

Users should be able to mark some sessions that they 
are interested in and retrieve their own current wishlist. The following 
endpoints are associated with the Wishlist functionality:

addSessionToWishlist(SessionKey) 
   -- adds the session to the user's list of sessions they are interested in 
      attending. Wishlist is open to all conferences.

getSessionsInWishlist() 
   -- query for all the sessions in a conference that the user is interested in

--------------------------------------------------------------------------------

Task 4: 
When a new session is added to a conference, the speaker is checked in
createSession(SessionForm, websafeConferenceKey). If there is more than one 
session by this speaker, he/she is added to the SpeakerDictionary in ndb as a 
key (speaker name) value pair (number of times speaker is appearing) and also 
added as a new Memcache entry that features the speaker.

getFeaturedSpeaker()
   -- Reads and returns featured speaker from memcache entry 
   
2) models.py
################################################################################
The models file contains all of the classes for storing and communicating data.
Specifically, they are sub-classes of the ndb.Model class for storing into NDB 
datastore and messages.Message class for communicating data in the form of 
ProtoRPC messages to and from endpoints.

New classes include: Session (sub-class of ndb.Model and child of specific 
Conference), SessionForm & SessionForms (protoRPC messages) and 
SpeakerDict(sub-class of ndb.Model which is used to store a dictionary in NDB 
using the PickleProperty).

Session class consists of the following fields:
    sessionName = ndb.StringProperty(required=True)
    highlights = ndb.StringProperty()
    speaker = ndb.StringProperty()
    duration = ndb.IntegerProperty()
    typeOfSession = ndb.StringProperty(repeated=True)
    Date = ndb.DateProperty()
    startTime = ndb.TimeProperty()

Speaker is implemented using a string for simplicity's sake. 

SessionForm mirrors the Session class with all the same properties but also 
includes the confwebsafeKey for the parent conference to be passed in.

SessionForms is a repeated set of SessionForm.

Class SpeakerDict(ndb.Model) has the following two fields
    identifier= ndb.IntegerProperty(default = 1234)
    speaker_num = ndb.PickleProperty(default={})
which is basically a dictionary that is stored in ndb using the pickleproperty
and a hardcoded identifier for easy extraction/query.

The remainder of the file was given.


3) settings.py
################################################################################
File contains web client id generated by GAE to authorize the web application

4) utils.py
################################################################################
File contains only one function: getUserId which does what it states.

5) main.py
################################################################################
This file is responsible for Tasks such as: sending out an email alert for a new
created conference, setting announcement handler, and checking featured speaker
handler.

6) app.yaml
################################################################################
Contains application id as well as url handlers.


7) cron.yaml
################################################################################
Sets cron job settings for announcements.


8) index.yaml
################################################################################
Contains indexes necessary for complex/composite queries.



9)  ./templates
################################################################################
Folder contains all the HTML templates necessary for rendering all available 
urls in web application.

10) ./static
################################################################################
Folder contains css file for styling HTML templates.


[1]: https://cloud.google.com/appengine/downloads