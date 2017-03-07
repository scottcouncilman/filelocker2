# -*- coding: utf-8 -*-
import re
import os
import datetime
import cherrypy
from lib.SQLAlchemyTool import session
import sqlalchemy
from Cheetah.Template import Template
from lib.Constants import Actions
from lib import Encryption
from lib.Models import *
from lib import AccountService
from lib import FileService
from lib import ShareService
from lib.Formatters import *
__author__="wbdavis"
__date__ ="$Sep 25, 2011 9:36:56 PM$"

class RootController:
    import FileController
    import ShareController
    import MessageController
    import AdminController
    import AccountController
    share = ShareController.ShareController()
    file = FileController.FileController()
    account = AccountController.AccountController()
    admin = AdminController.AdminController()
    message = MessageController.MessageController()
    #DropPrivileges(cherrypy.engine, umask=077, uid='nobody', gid='nogroup').subscribe()

    def __init__(self):
        pass

    @cherrypy.expose
    def local(self, **kwargs):
        raise cherrypy.HTTPRedirect("%s/login?local=%s" % (cherrypy.request.app.config['filelocker']['root_url'], str(True)))

    @cherrypy.expose
    def login(self, **kwargs):
        msg, errorMessage, config = ( None, None, cherrypy.request.app.config['filelocker'])
        authType = session.query(ConfigParameter).filter(ConfigParameter.name=="auth_type").one().value
        orgConfig = get_config_dict_from_objects(session.query(ConfigParameter).filter(ConfigParameter.name.like('org_%')).all())
        if kwargs.has_key("msg"):
            msg = kwargs['msg']
        if kwargs.has_key("local") and kwargs['local']==str(True):
            authType = "local"

        loginPage = config['root_url'] + "/process_login"
        if msg is not None and str(strip_tags(msg))=="1":
            errorMessage = "Invalid username or password"
        elif msg is not None and str(strip_tags(msg))=="2":
            errorMessage = "You have been logged out of the application"
        elif msg is not None and str(strip_tags(msg))=="3":
            errorMessage = "Password cannot be blank"

        if authType == "ldap" or authType == "local":
            currentYear = datetime.date.today().year
            footerText = str(Template(file=get_template_file('footer_text.tmpl'), searchList=[locals(),globals()]))
            tpl = Template(file=get_template_file('login.tmpl'), searchList=[locals(),globals()])
            return str(tpl)
        elif authType == "cas":
            raise cherrypy.HTTPRedirect(config['root_url'])
        # PSM lines 65-67
        elif authType == "saml":
            username = cherrypy.request.headers['X-UID']
            self.process(username, password)
        else:
            cherrypy.log.error("[system] [login] [No authentication variable set in config]")
            raise cherrypy.HTTPError(403, "No authentication mechanism")

    @cherrypy.expose
    @cherrypy.tools.requires_login()
    def logout(self):
        config = cherrypy.request.app.config['filelocker']
        orgConfig = get_config_dict_from_objects(session.query(ConfigParameter).filter(ConfigParameter.name.like('org_%')).all())
        authType = session.query(ConfigParameter).filter(ConfigParameter.name=="auth_type").one().value
        if authType == "cas":
            from lib.CAS import CAS
            casUrl = session.query(ConfigParameter).filter(ConfigParameter.name=="cas_url").one().value
            casConnector = CAS(casUrl)
            casLogoutUrl =  casConnector.logout_url()+"?redirectUrl="+config['root_url']+"/logout_cas"
            currentYear = datetime.date.today().year
            footerText = str(Template(file=get_template_file('footer_text.tmpl'), searchList=[locals(),globals()]))
            tpl = Template(file=get_template_file('cas_logout.tmpl'), searchList=[locals(), globals()])
            cherrypy.session['user'], cherrypy.response.cookie['filelocker']['expires'] = None, 0
            return str(tpl)
        else:
            cherrypy.session['user'], cherrypy.response.cookie['filelocker']['expires'] = None, 0
            raise cherrypy.HTTPRedirect(config['root_url']+'/login?msg=2')

    @cherrypy.expose
    def logout_cas(self):
        from lib.CAS import CAS
        config = cherrypy.request.app.config['filelocker']
        orgConfig = get_config_dict_from_objects(session.query(ConfigParameter).filter(ConfigParameter.name.like('org_%')).all())
        currentYear = datetime.date.today().year
        footerText = str(Template(file=get_template_file('footer_text.tmpl'), searchList=[locals(),globals()]))
        tpl = Template(file=get_template_file('cas_logout_confirmation.tmpl'), searchList=[locals(), globals()])
        return str(tpl)

    @cherrypy.expose
    def process_login(self, local, username, password, **kwargs):
        rootURL, local = cherrypy.request.app.config['filelocker']['root_url'], False
        if kwargs.has_key("local") and local ==str(True):
            local = True
        username = strip_tags(username)

        if password is None or password == "":
            raise cherrypy.HTTPRedirect("%s/login?msg=3&local=%s" % (rootURL, str(local)))
        else:
            directory = AccountService.ExternalDirectory(local)
            if directory.authenticate(username, password):
                currentUser = AccountService.get_user(username, True) #if they are authenticated and local, this MUST return a user object
                if currentUser is not None:
                    if not currentUser.authorized:
                        raise cherrypy.HTTPError(403, "You do not have permission to access this system")
                    session.add(AuditLog(cherrypy.session.get("user").id, "Login", "User %s logged in successfully from IP %s" % (currentUser.id, cherrypy.request.remote.ip)))
                    session.commit()
                    raise cherrypy.HTTPRedirect(rootURL)
                else: #This should only happen in the case of a user existing in the external directory, but having never logged in before
                    try:
                        newUser = directory.lookup_user(username)
                        AccountService.install_user(newUser)
                        currentUser = AccountService.get_user(username, True)
                        if currentUser is not None and currentUser.authorized != False:
                            raise cherrypy.HTTPRedirect(rootURL)
                        else:
                            raise cherrypy.HTTPError(403, "You do not have permission to access this system")
                    except Exception, e:
                        return "Unable to install user: %s" % str(e)
            else:
                raise cherrypy.HTTPRedirect("%s/login?msg=1&local=%s" % (rootURL, str(local)))

    @cherrypy.expose
    def css(self, style):
        rootURL = cherrypy.request.app.config['filelocker']['root_url']
        cherrypy.response.headers['Content-Type'] = 'text/css'
        staticDir = os.path.join(rootURL,"static")
        styleFile = str("%s.css" % style)
        return str(Template(file=get_template_file(styleFile), searchList=[locals(),globals()]))

    @cherrypy.expose
    @cherrypy.tools.requires_login()
    def index(self, **kwargs):
        config = cherrypy.request.app.config['filelocker']
        authType = session.query(ConfigParameter).filter(ConfigParameter.name=="auth_type").one().value
        orgConfig = get_config_dict_from_objects(session.query(ConfigParameter).filter(ConfigParameter.name.like('org_%')).all())
        user, originalUser = (cherrypy.session.get("user"),  cherrypy.session.get("original_user"))
        maxDays = int(session.query(ConfigParameter).filter(ConfigParameter.name=='max_file_life_days').one().value)
        roles = session.query(User).filter(User.id == user.id).one().roles
        currentYear = datetime.date.today().year
        startDateFormatted, endDateFormatted = None, None
        today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        sevenDays = datetime.timedelta(days=7)
        sevenDaysAgo = today - sevenDays
        sevenDaysAgo = sevenDaysAgo.replace(hour=0, minute=0, second=0, microsecond=0)
        defaultExpiration = datetime.date.today() + (datetime.timedelta(days=maxDays))
        startDateFormatted = sevenDaysAgo
        endDateFormatted = today
        messageSearchWidget = self.account.get_search_widget("messages")
        geoTagging = get_config_dict_from_objects([session.query(ConfigParameter).filter(ConfigParameter.name=='geotagging').one()])['geotagging']
        banner = session.query(ConfigParameter).filter(ConfigParameter.name=='banner').one().value
        defaultQuota = int(session.query(ConfigParameter).filter(ConfigParameter.name=='default_quota').one().value)
        header = Template(file=get_template_file('header.tmpl'), searchList=[locals(),globals()])
        lightboxen = str(Template(file=get_template_file('lightboxen.tmpl'), searchList=[locals(),globals()]))
        footerText = str(Template(file=get_template_file('footer_text.tmpl'), searchList=[locals(),globals()]))
        footer = Template(file=get_template_file('footer.tmpl'), searchList=[locals(),globals()])
        filesSection = self.files()
        indexHTML = str(header) + str(filesSection) + str(footer)
        self.saw_banner()
        return str(indexHTML)

    @cherrypy.expose
    @cherrypy.tools.requires_login()
    def saw_banner(self, **kwargs):
        cherrypy.session['sawBanner'] = True
        return ""

    @cherrypy.expose
    def sign_tos(self, **kwargs):
        config = cherrypy.request.app.config['filelocker']
        orgConfig = get_config_dict_from_objects(session.query(ConfigParameter).filter(ConfigParameter.name.like('org_%')).all())
        if cherrypy.session.has_key("user") and cherrypy.session.get("user") is not None:
            user = cherrypy.session.get("user")
            if kwargs.has_key('action') and kwargs['action']=="sign":
                attachedUser = session.query(User).filter(User.id == user.id).one()
                attachedUser.date_tos_accept = datetime.datetime.now()
                cherrypy.session['user'] = attachedUser.get_copy()
                session.commit()
                raise cherrypy.HTTPRedirect(config['root_url'])
            else:
                currentYear = datetime.date.today().year
                footerText = str(Template(file=get_template_file('footer_text.tmpl'), searchList=[locals(),globals()]))
                return str(Template(file=get_template_file('tos.tmpl'), searchList=[locals(),globals()]))
        else:
            raise cherrypy.HTTPRedirect(config['root_url'])

    @cherrypy.expose
    @cherrypy.tools.requires_login()
    def admin_console(self, **kwargs):
        user, config = cherrypy.session.get("user"), cherrypy.request.app.config['filelocker']
        orgConfig = get_config_dict_from_objects(session.query(ConfigParameter).filter(ConfigParameter.name.like('org_%')).all())
        templateFiles = os.listdir(os.path.join(config['root_path'], "view"))
        configParameters = session.query(ConfigParameter).order_by(ConfigParameter.name).all()
        flUsers = session.query(User).slice(0,50)
        flRoles = session.query(Role)
        totalFileCount = session.query(func.count(File.id)).scalar()
        totalUserCount = session.query(func.count(User.id)).scalar()
        totalMessageCount = session.query(func.count(Message.id)).scalar()
        currentUsersList = []
        currentUploads = len(cherrypy.file_uploads)
        logsFile = open(cherrypy.config["log.error_file"])
        logs = tail(logsFile, 50)
        attributes = AccountService.get_shareable_attributes_by_user(user)
        currentUserIds = []
        sessionCache = {}
        sessionCache = cherrypy.session.cache
        for key in sessionCache.keys():
            try:
                if sessionCache[key][0].has_key('user') and sessionCache[key][0]['user'] is not None and sessionCache[key][0]['user'].id not in currentUserIds:
                    currentUser = sessionCache[key][0]['user']
                    currentUsersList.append(currentUser)
                    currentUserIds.append(currentUser.id)
            except Exception, e:
                cherrypy.log.error("[%s] [admin] [Unable to read user session: %s]" % (user.id, str(e)))
        tpl = Template(file=get_template_file('admin.tmpl'), searchList=[locals(),globals()])
        return str(tpl)

    @cherrypy.expose
    @cherrypy.tools.requires_login()
    def history(self, userId=None, startDate=None, endDate=None, logAction=None, format="html", **kwargs):
        sMessages, fMessages, user, role= ([],[],cherrypy.session.get("user"),cherrypy.session.get("current_role"))
        config = cherrypy.request.app.config['filelocker']
        orgConfig = get_config_dict_from_objects(session.query(ConfigParameter).filter(ConfigParameter.name.like('org_%')).all())

        userId = strip_tags(userId) if strip_tags(userId) != None else user.id
        if (userId != user.id and AccountService.user_has_permission(user, "admin")==False):
            raise cherrypy.HTTPError(403)
        actionList, actionLogList = ([], [])
        try:
            startDateFormatted, endDateFormatted = None, None
            sevenDays = datetime.timedelta(days=7)
            today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            sevenDaysAgo = today - sevenDays
            sevenDaysAgo = sevenDaysAgo.replace(hour=0, minute=0, second=0, microsecond=0)
            if startDate is not None:
                try:
                    startDateFormatted = datetime.datetime(*time.strptime(strip_tags(startDate), "%m/%d/%Y")[0:5])
                except Exception, e:
                    fMessages.append("Start date was not properly formatted")
                    startDateFormatted = sevenDaysAgo
            else:
                startDateFormatted = sevenDaysAgo
            if endDate is not None:
                try:
                    endDateFormatted = datetime.datetime(*time.strptime(strip_tags(endDate), "%m/%d/%Y")[0:5])
                except Exception, e:
                    fMessages.append("End date was not properly formatted")
                    endDateFormatted = today
            else:
                endDateFormatted = today
            actionLogListAtt = session.query(AuditLog).filter(and_(AuditLog.date >= startDateFormatted, AuditLog.date <= (endDateFormatted + datetime.timedelta(days=1)))).filter(or_(AuditLog.initiator_user_id==userId, AuditLog.affected_user_id==userId))

            if logAction is None or logAction == "" or logAction == "all_minus_login":
                logAction = "all_minus_login"
                actionLogListAtt = actionLogListAtt.filter(AuditLog.action != Actions.LOGIN)
            else:
                logAction = strip_tags(logAction)
                actionLogListAtt = actionLogListAtt.filter(AuditLog.action == logAction)

            for log in actionLogListAtt.all():
                log.display_class = "%s_%s" % ("audit", log.action.replace(" ", "_").lower())
                log.display_class = re.sub('_\(.*?\)', '', log.display_class) # Removes (You) and (Recipient) from Read Message actions
                actionLogList.append(log)
            actionNames = session.query(AuditLog.action).filter(or_(AuditLog.initiator_user_id==userId, AuditLog.affected_user_id==userId)).distinct()
            #for actionLog in actionNames:
                #if actionLog not in actionList:
                    #actionList.append(actionLog.action)
            actionList = Actions.ACTION_LIST
        except Exception, e:
            fMessages.append(str(e))
        if format == "html":
            tpl = Template(file=get_template_file('history.tmpl'), searchList=[locals(),globals()])
            return str(tpl)
        else:
            actionLogJSONlist = []
            for actionLog in actionLogList:
                actionLogJSONlist.append(actionLog.get_dict())
            return fl_response(sMessages, fMessages, format, data=actionLogJSONlist)

    @cherrypy.expose
    @cherrypy.tools.requires_login()
    def files(self, **kwargs):
        user, role, defaultExpiration, uploadRequests, userFiles, userShareableAttributes,attributeFilesDict,sharedFiles = (cherrypy.session.get("user"), cherrypy.session.get("current_role"), None, [], [], [], {}, [])
        config = cherrypy.request.app.config['filelocker']
        orgConfig = get_config_dict_from_objects(session.query(ConfigParameter).filter(ConfigParameter.name.like('org_%')).all())
        maxDays = int(session.query(ConfigParameter).filter(ConfigParameter.name=='max_file_life_days').one().value)
        geoTagging = get_config_dict_from_objects([session.query(ConfigParameter).filter(ConfigParameter.name=='geotagging').one()])['geotagging']
        adminEmail = session.query(ConfigParameter).filter(ConfigParameter.name=='admin_email').one().value
        defaultExpiration = datetime.date.today() + (datetime.timedelta(days=maxDays))
        userFiles = self.file.get_user_file_list(format="list")
        if role is None:
            uploadRequests = session.query(UploadRequest).filter(UploadRequest.owner_id==user.id).all()
            userShareableAttributes = AccountService.get_shareable_attributes_by_user(user)
            attributeFilesDict = ShareService.get_files_shared_with_user_by_attribute(user)
            sharedFiles = ShareService.get_files_shared_with_user(user)
        else:
            userShareableAttributes = AccountService.get_shareable_attributes_by_role(role)
        tpl = Template(file=get_template_file('files.tmpl'), searchList=[locals(),globals()])
        return str(tpl)

    @cherrypy.expose
    def help(self, **kwargs):
        defaultQuota = int(session.query(ConfigParameter).filter(ConfigParameter.name=='default_quota').one().value)
        maxDays = int(session.query(ConfigParameter).filter(ConfigParameter.name=='max_file_life_days').one().value)
        geoTagging = get_config_dict_from_objects([session.query(ConfigParameter).filter(ConfigParameter.name=='geotagging').one()])['geotagging']
        tpl = Template(file=get_template_file('halp.tmpl'), searchList=[locals(),globals()])
        return str(tpl)

    @cherrypy.expose
    @cherrypy.tools.requires_login()
    def manage_groups(self, **kwargs):
        user, config = cherrypy.session.get("user"), cherrypy.request.app.config['filelocker']
        orgConfig = get_config_dict_from_objects(session.query(ConfigParameter).filter(ConfigParameter.name.like('org_%')).all())
        groups = session.query(Group).filter(Group.owner_id==user.id).all()
        tpl = Template(file=get_template_file('manage_groups.tmpl'), searchList=[locals(),globals()])
        return str(tpl)

    @cherrypy.expose
    def toobig(self, **kwargs):
        return fl_response([], ['File is too big'], "json")

    @cherrypy.expose
    def upload_request(self, requestId=None, msg=None, **kwargs):
        user = None
        messages, uploadRequest, requestId, config = [], None, strip_tags(requestId), cherrypy.request.app.config['filelocker']
        orgConfig = get_config_dict_from_objects(session.query(ConfigParameter).filter(ConfigParameter.name.like('org_%')).all())
        if msg is not None and int(msg) == 1: messages.append("You must supply a valid ID and password to upload files for this request")
        if msg is not None and int(msg) == 2: messages.append("Unable to load upload request")
        if msg is not None and int(msg) == 3: messages.append("Invalid password")
        requestId = strip_tags(requestId)
        if cherrypy.session.has_key("uploadRequest"):
            raise cherrypy.HTTPRedirect(config['root_url']+'/upload_request_uploader?requestId=%s' % requestId)
        elif requestId is not None:
            try:
                uploadRequest = session.query(UploadRequest).filter(UploadRequest.id == requestId).one()
                if (uploadRequest.type == "single" and uploadRequest.password == None):
                    raise cherrypy.HTTPRedirect(config['root_url']+'/upload_request_uploader?requestId=%s' % requestId)
            except sqlalchemy.orm.exc.NoResultFound, nrf:
                messages.append("Invalid upload request ID")
        currentYear = datetime.date.today().year
        geoTagging = get_config_dict_from_objects([session.query(ConfigParameter).filter(ConfigParameter.name=='geotagging').one()])['geotagging']
        banner = session.query(ConfigParameter).filter(ConfigParameter.name=='banner').one().value
        headerHTML = str(Template(file=get_template_file('header.tmpl'), searchList=[locals(),globals()]))
        footerText = str(Template(file=get_template_file('footer_text.tmpl'), searchList=[locals(),globals()]))
        footerHTML = str(Template(file=get_template_file('footer.tmpl'), searchList=[locals(),globals()]))
        tpl = str(Template(file=get_template_file('public_upload_request.tmpl'), searchList=[locals(),globals()]))
        uploadRequestHTML = headerHTML+tpl+footerHTML
        return uploadRequestHTML

    @cherrypy.expose
    def upload_request_uploader(self, requestId=None, password=None, **kwargs):
        user = None
        format = "content_only" if kwargs.has_key("format") and kwargs["format"] == "content_only" else "html"
        requestOwner, uploadRequest, tpl, messages, config = (None, None, None, [], cherrypy.request.app.config['filelocker'])
        orgConfig = get_config_dict_from_objects(session.query(ConfigParameter).filter(ConfigParameter.name.like('org_%')).all())
        maxDays = int(session.query(ConfigParameter).filter(ConfigParameter.name=='max_file_life_days').one().value)
        defaultExpiration = datetime.date.today() + (datetime.timedelta(days=maxDays))
        requestFiles = []
        requestId = strip_tags(requestId)
        if requestId is not None:
            if cherrypy.session.has_key("uploadRequest"):
                if cherrypy.session.get("uploadRequest").id != requestId:
                    #TODO session check deletion
                    del(cherrypy.session['uploadRequest'])
            if cherrypy.session.has_key("uploadRequest"): #Their requestId and the session uploadTicket's ID matched, let them keep the session
                uploadRequestId = cherrypy.session.get("uploadRequest").id
                uploadRequest = session.query(UploadRequest).filter(UploadRequest.id == uploadRequestId).scalar()
                if uploadRequest is None: #Expired request, but they still have a valid session to view file
                    uploadRequest = cherrypy.session.get("uploadRequest")
                    uploadRequest.expired = True
            elif password is None or password =="": #If they come in with a ticket - fill it in and prompt for password
                try:
                    uploadRequest = session.query(UploadRequest).filter(UploadRequest.id == requestId).one()
                    if uploadRequest.password == None and uploadRequest.type == "single":
                        cherrypy.session['uploadRequest'] = uploadRequest.get_copy()
                    else:
                        messages.append("This upload request requires a password before you can upload files")
                        uploadRequest = None
                        raise cherrypy.HTTPError(500, "Invalid password") if format == "content_only" else cherrypy.HTTPRedirect(config['root_url']+'/upload_request?requestId=%s&msg=3' % requestId)
                    requestOwner = session.query(User).filter(User.id == uploadRequest.owner_id).one()
                except cherrypy.HTTPError, httpe:
                    raise httpe
                except cherrypy.HTTPRedirect, httpr:
                    raise httpr
                except Exception, e:
                    messages.append(str(e))
            elif password is not None and password!="": # if they do have a password and requestId, try to load the whole upload ticket
                uploadRequest = session.query(UploadRequest).filter(UploadRequest.id == requestId).one()
                if Encryption.compare_password_hash(password, uploadRequest.password):
                    cherrypy.session['uploadRequest'] = uploadRequest.get_copy()
                    requestOwner = session.query(User).filter(User.id == uploadRequest.owner_id).one()
                else:
                    uploadRequest = None
                    raise cherrypy.HTTPError(500, "Invalid password") if format == "content_only" else cherrypy.HTTPRedirect(config['root_url']+'/upload_request?requestId=%s&msg=3' % requestId)
        elif cherrypy.session.has_key("uploadRequest"):
            uploadRequest = cherrypy.session.get("uploadRequest")
            requestOwner = session.query(User).filter(User.id == uploadRequest.owner_id).one()
        else:
            raise cherrypy.HTTPError(500, "Unable to load upload request") if format == "content_only" else cherrypy.HTTPRedirect("%s/upload_request?msg=1" % (config['root_url']))

        if uploadRequest is not None:
            fileList = session.query(File).filter(File.upload_request_id==uploadRequest.id).all()
            for flFile in fileList:
                flFile.documentType = "document"
                requestFiles.append({'fileName': flFile.name, 'fileId': flFile.id, 'fileOwnerId': flFile.owner_id, 'fileSizeBytes': flFile.size, 'fileUploadedDatetime': flFile.date_uploaded.strftime("%m/%d/%Y") if flFile.date_uploaded is not None else "" , 'fileExpirationDatetime': flFile.date_expires.strftime("%m/%d/%Y") if flFile.date_expires is not None else "", 'filePassedAvScan':flFile.passed_avscan, 'documentType': flFile.document_type})
            tpl = ""
            currentYear = datetime.date.today().year
            footerText = str(Template(file=get_template_file('footer_text.tmpl'), searchList=[locals(),globals()]))
            tpl = str(Template(file=get_template_file('public_upload_request_uploader.tmpl'), searchList=[locals(),globals()]))
        else:
            raise cherrypy.HTTPError(500, "Unable to load upload request") if format == "content_only" else cherrypy.HTTPRedirect("%s/upload_request?msg=2" % (config['root_url']))
        geoTagging = get_config_dict_from_objects([session.query(ConfigParameter).filter(ConfigParameter.name=='geotagging').one()])['geotagging']
        banner = session.query(ConfigParameter).filter(ConfigParameter.name=='banner').one().value
        headerHTML = str(Template(file=get_template_file('header.tmpl'), searchList=[locals(),globals()]))
        footerText = str(Template(file=get_template_file('footer_text.tmpl'), searchList=[locals(),globals()]))
        footerHTML = str(Template(file=get_template_file('footer.tmpl'), searchList=[locals(),globals()]))
        uploadRequestUploaderHTML = ""
        if format == "content_only":
        	uploadRequestUploaderHTML = tpl
        else:
        	uploadRequestUploaderHTML = headerHTML+tpl+footerHTML
        return uploadRequestUploaderHTML

    @cherrypy.expose
    def public_download(self, shareId, **kwargs):
        user = None
        message, publicShare, config = None, None, cherrypy.request.app.config['filelocker']
        orgConfig = get_config_dict_from_objects(session.query(ConfigParameter).filter(ConfigParameter.name.like('org_%')).all())
        cherrypy.response.timeout = 36000
        shareId = strip_tags(shareId)

        try:
            publicShare = session.query(PublicShare).filter(PublicShare.id==shareId).one()
            if cherrypy.session.has_key("public_share_id") == False or cherrypy.session.get("public_share_id") != publicShare.id:
                password = kwargs['password'] if kwargs.has_key("password") else None
                if publicShare.password == None or (password is not None and Encryption.compare_password_hash(password, publicShare.password)):
                    cherrypy.session['public_share_id'] = publicShare.id
                elif password == None:
                    message = "This file share is password protected."
                    publicShare = None
                elif password is not None and Encryption.compare_password_hash(password, publicShare.password) == False:
                    message = "Invalid password"
                    publicShare = None
                else:
                    publicShare = None
        except sqlalchemy.orm.exc.NoResultFound:
            message = "Invalid Share ID"
            shareId = None
        except Exception, e:
            message = "Unable to access download page: %s " % str(e)
        currentYear = datetime.date.today().year
        geoTagging = get_config_dict_from_objects([session.query(ConfigParameter).filter(ConfigParameter.name=='geotagging').one()])['geotagging']
        banner = session.query(ConfigParameter).filter(ConfigParameter.name=='banner').one().value
        headerHTML = str(Template(file=get_template_file('header.tmpl'), searchList=[locals(),globals()]))
        footerText = str(Template(file=get_template_file('footer_text.tmpl'), searchList=[locals(),globals()]))
        footerHTML = str(Template(file=get_template_file('footer.tmpl'), searchList=[locals(),globals()]))
        tpl = str(Template(file=get_template_file('public_download_landing.tmpl'), searchList=[locals(),globals()]))
        publicDownloadHTML = headerHTML+tpl+footerHTML
        return publicDownloadHTML

    @cherrypy.expose
    def get_server_messages(self, format="json", **kwargs):
        sMessages, fMessages = [], []
        if cherrypy.session.has_key("sMessages") and cherrypy.session.has_key("fMessages"):
            for message in cherrypy.session.get("sMessages"):
                if message not in sMessages: 
                    #Interestingly, either the browser or the ajax upload script tries to re-submit a rejected file a few times resulting in duplicate messages
                    sMessages.append(message)
            for message in cherrypy.session.get("fMessages"):
                if message not in fMessages:
                    fMessages.append(message)
            (cherrypy.session["sMessages"], cherrypy.session["fMessages"]) = [], []
        return fl_response(sMessages, fMessages, format)

#    @cherrypy.expose
#    @cherrypy.tools.requires_login()
#    def download_filelocker_client(self, platform, **kwargs):
#        clientPath = os.path.join(cherrypy.request.app.config['root_path'], "static", "clients")
#        if platform=="cli":
#            return serve_file(os.path.join(clientPath,"cliFilelocker.py"), "application/x-download", "attachment")
        #elif platform="windows":
            #return serve_file(os.path.join(fl.clientPath,"windowsFilelocker.exe"), "application/x-download", "attachment")
        #elif platform="macintosh":
            #return serve_file(os.path.join(fl.clientPath,"macintoshFilelocker.dmg"), "application/x-download", "attachment")
        #elif platform="ios":
            #return serve_file(os.path.join(fl.clientPath,"iosFilelocker.app"), "application/x-download", "attachment")
        #elif platform="android":
            #return serve_file(os.path.join(fl.clientPath,"androidFilelocker.app"), "application/x-download", "attachment")
