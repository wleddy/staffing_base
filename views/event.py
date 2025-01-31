from flask import request, session, g, redirect, url_for, abort, \
     render_template, flash, Blueprint, Response
from shotglass2.shotglass import get_site_config
from shotglass2.users.admin import login_required, table_access_required
from shotglass2.takeabeltof.utils import render_markdown_for, printException, cleanRecordID, Numeric
from shotglass2.takeabeltof.date_utils import date_to_string, getDatetimeFromString, local_datetime_now, datetime_as_string
from staffing_base.models import Event, Location, ActivityType, Client, EventDateLabel, Job, JobRole, UserJob
from shotglass2.users.models import User
from staffing_base.views.announcements import send_signup_email
from staffing_base.views.job import get_job_list_for_event, coerce_datetime
from staffing_base.views.signup import get_job_rows
from datetime import timedelta

mod = Blueprint('event',__name__, template_folder='templates/event', url_prefix='/event')


def setExits():
    g.listURL = url_for('.display')
    g.editURL = url_for('.edit')
    g.deleteURL = url_for('.delete')
    g.title = 'Events'


from shotglass2.takeabeltof.views import TableView
PRIMARY_TABLE = Event
# this handles table list and record delete
@mod.route('/<path:path>',methods=['GET','POST',])
@mod.route('/<path:path>/',methods=['GET','POST',])
@mod.route('/',methods=['GET','POST',])
@table_access_required(PRIMARY_TABLE)
def display(path=None):
    # import pdb;pdb.set_trace()
    setExits()
    g.title = "{} Record List".format(g.title)

    view = TableView(PRIMARY_TABLE,g.db)
    # optionally specify the list fields
    view.list_fields = [
            {'name':'id','label':'ID','class':'w3-hide-small','search':True},
            {'name':'activity_title','label':'Title'},
            {'name':'status',},
            {'name':'event_start_date','label':'Event Date','search':'date','type':"datetime"},
            {'name':'prep_status',},
            {'name':'event_contract_date','label':'Contract Date','search':'date','type':'date'},
        ]
    
    view.export_fields = []
    view.export_fields.append({'name':'activity_title',})
    view.export_fields.append({'name':'event_title',})
    view.export_fields.append({'name':'status',})
    view.export_fields.append({'name':'event_start_date','type':'date'})
    view.export_fields.append({'name':'prep_status',})
    view.export_fields.append({'name':'event_size',})
    view.export_fields.append({'name':'number_served',})
    view.export_fields.append({'name':'tips_received',})
    view.export_fields.append({'name':'event_contract_date','label':'Contract Date','type':'date'})
    view.export_fields.append({'name':'event_per_event_contract_price','label':'Per Event Price'})
    view.export_fields.append({'name':'event_total_contract_price','label':'Total Contract Price'})
    
    return view.dispatch_request()
  
    
@mod.route('/edit/',methods=['POST',])
@mod.route('/edit/<int:id>',methods=['GET','POST',])
@mod.route('/edit/<int:id>/',methods=['GET','POST',])
@mod.route('/edit/<int:id>/<int:activity_id>',methods=['GET','POST',])
@mod.route('/edit/<int:id>/<int:activity_id>/',methods=['GET','POST',])
@table_access_required(Event)
def edit(id=0,activity_id=None):
    setExits()
    g.title = 'Edit Event Record'
    if cleanRecordID(id) == 0:
        g.cancelURL = g.deleteURL
        
    return render_edit_form(id,activity_id)
    
    
@mod.route('/edit_from_activity/',methods=['POST',])
@mod.route('/edit_from_activity/<int:id>/<int:activity_id>',methods=['GET','POST',])
@mod.route('/edit_from_activity/<int:id>/<int:activity_id>/',methods=['GET','POST',])
@table_access_required(Event)
def edit_from_activity(id=0,activity_id=-1):
    """Create or edit an Event record from the Activity input form"""
    #import pdb;pdb.set_trace()
    setExits()
    g.title = 'Edit Event Record'
    
    if request.form:
        id = cleanRecordID(request.form.get("id"))
        activity_id = cleanRecordID(request.form.get("activity_id"))
        
    # Return to Activty record when done with edit
    g.editURL = url_for('event.edit_from_activity')
    g.listURL = url_for('activity.edit') + str(cleanRecordID(activity_id))
    g.deleteURL = url_for('event.delete_from_activity')+ str(cleanRecordID(activity_id)) + "/" 
    if cleanRecordID(id) == 0:
        g.cancelURL = g.deleteURL
        

    return render_edit_form(id,activity_id)
    
    
def render_edit_form(id,activity_id):
    #import pdb;pdb.set_trace()
    id = cleanRecordID(id)
    activity_id = cleanRecordID(activity_id)
        
    if request.form:
        id = cleanRecordID(request.form.get("id"))
        activity_id = cleanRecordID(request.form.get("activity_id"))
        
    event = Event(g.db)
    clients = Client(g.db).select()
    event_date_labels=EventDateLabel(g.db).select()
    
    if id <= 0 and activity_id <= 0:
        #can't create a new record without an activity link
        flash("Unknown Activity ID")
        return abort(404)
        
    if id > 0:
        rec = event.get(id)
        if not rec:
            flash("Record Not Found")
            return redirect(g.listURL)
    else:
        rec = event.new()
        user = User(g.db).get(g.user)
        rec.manager_user_id = user.id
        rec.activity_id = activity_id

        # set default begin and end date to Now
        rec.event_start_date = datetime_as_string(local_datetime_now())
        rec.event_end_date = datetime_as_string(local_datetime_now()+timedelta(minutes=60))
        
        event.save(rec)
        g.db.commit()
        g.cancelURL = g.cancelURL + str(rec.id)
        # fetch the record again to load the related activity data
        rec = event.get(rec.id)

    if request.form:
        # import pdb;pdb.set_trace()
        
        # set Service start and end to None in rec. 
        # values will be set if Service start and end are in form
        # or set == to event times in valid_input method
        rec.service_start_date = None
        rec.service_end_date = None
        rec.service_start_date_label_id = None
        rec.service_end_date_label_id = None
        # set all_day to default state
        rec.all_day_event = None
        
        event.update(rec,request.form)
        if 'exclude_from_calendar' in request.form:
            rec.exclude_from_calendar = 1
        else:
            rec.exclude_from_calendar = 0
            
        rec.location_id = cleanRecordID(request.form.get('location_id',-1))
        # ensure that web address is absolute
        if rec.client_website.strip():
            parts = rec.client_website.partition("//")
            data_part = [x.strip() for x in parts] #convert to a list to make it simplier
                
            if data_part[0] != '' and data_part[1] == '' and data_part[2] == '':
                # no // present. host name at [0]
                data_part[2] = data_part[0]
                
            if data_part[2].strip() == '':
                rec.client_website = None
                
            elif data_part[0][:4] != 'http':
                rec.client_website = 'http://' + data_part[2]
            
        if valid_input(rec):
            event.save(rec)
            g.db.commit()
            return redirect(g.listURL)
        
    # get lists for form
    client = Client(g.db).get(rec.client_id)
    locations = Location(g.db).select()
    # only users of sufficient rank can manage an event
    where = "user.id in (select user_id from user_role where role_id in (select role.id from role where rank >= {}))".format(get_site_config().get('MINIMUM_MANAGER_RANK',100))
    event_managers = User(g.db).select(where=where)
    job_embed_list = get_job_list_for_event(rec.id)
       
        
    return render_template('event_edit.html',
        rec=rec,
        locations=locations,
        event_managers=event_managers,
        clients=clients,client=client,
        job_embed_list=job_embed_list,
        event_date_labels=event_date_labels,
        )
    
    
@mod.route('/manage_event/',methods=['GET','POST',])
@mod.route('/manage_event/<int:id>/',methods=['GET','POST',])
@table_access_required(Event)
def manage_event(id=0):
    """Delete, move or copy the specifed event and it's jobs.
    In the case of move or copy, include the option to move/copy the assignments
    
    This is an auax request
    """
    
    #import pdb;pdb.set_trace()
    action = request.args.get('action')
    new_date=request.form.get('new_date','')
    move_assignments=request.form.get('move_assignments',"")
    try:
        move_assignments = int(move_assignments)
    except:
        move_assignments = ''
        
    id = cleanRecordID(request.form.get('id',id))
    
    if id < 1:
        return 'failure: That is not a valid event ID'
        
    if action not in [None,'copy','move','delete',]:
        return 'failure: That is not a valid action request'
    
    job_table = Job(g.db)
    user_job_table = UserJob(g.db)
    event_table=Event(g.db)
    event_rec = event_table.get(id)
    
    if not event_rec:
        return "failure: Event record not found."
        
    # the event start and end dates must be set for this to work
    if not event_rec.event_start_date or not event_rec.event_end_date:
        return "failure: You must set the start and end dates for the event first."
        
    dup_date = None
    if request.form and action != 'delete':
        # validate the new date for a copy or move
        try:
            dup_date = coerce_datetime(request.form.get('new_date',''),'23:00:00')
            if dup_date:
                # 12/22/19 - BL Now allow move or copy to past
                # # You can't move a set into the past
                # if dup_date < local_datetime_now():
                #     return "failure: You can't move or copy a set into the past"
                    
                #convert it to a string
                dup_date = date_to_string(dup_date,'iso_date') #'YYYY-MM-DD'
            else:
                return "failure: That is not a valid date"
        except Exception as e:
            mes = 'Got an error while processing the date'
            printException(mes,err=e)
            return "failure: {}".format(mes)
            
    if request.form: # and (dup_date or action == 'delete'):
        try:
            # stash a copy of the values of the original event record
            orig_event_dict = event_rec._asdict()
        
            user_job_recs = user_job_table.query('select user_job.* from user_job where job_id in (select job.id from job join event on event.id = job.event_id where event.id = {})'.format(event_rec.id))
            if action == 'delete' and user_job_recs:
                ## Don't delete if there are any assignmehnts
                return "failure: There are one or more users assigned to this event. You must remove the assignments first."
                
                
            if action != "delete":
                # Create or update the event
                if action == "copy":
                    #make a new event record
                    new_event_rec = event_table.new()
                    event_table.update(new_event_rec,orig_event_dict)
                    
                    # give it a fresh creation date
                    new_event_rec.created = local_datetime_now()
                    
                    # the planning fields need to be cleared
                    new_event_rec.prep_status = None
                    new_event_rec.event_size = None
                    new_event_rec.number_served = None
                    new_event_rec.tips_received = None
                    
                    event_table.save(new_event_rec)
                else:
                    new_event_rec=event_rec # to make it easier to refer by either name
                    
                new_event_rec.event_start_date = dup_date + new_event_rec.event_start_date[10:]
                new_event_rec.event_end_date = dup_date + new_event_rec.event_end_date[10:]
                new_event_rec.service_start_date = dup_date + new_event_rec.service_start_date[10:]
                new_event_rec.service_end_date = dup_date + new_event_rec.service_end_date[10:]
                event_table.save(new_event_rec)
            
            
                job_recs = job_table.select(where="event_id = {}".format(event_rec.id))
                #import pdb;pdb.set_trace()
                
                if job_recs:
                    for job_rec in job_recs:
                        ## copy or move
                        orig_job_id = job_rec.id
                        if action == 'copy':
                            job_rec.id = None #create a new job record
                            job_rec.event_id = new_event_rec.id
                            job_table.save(job_rec)
                            
                            #copy the skills required
                            job_role_table = JobRole(g.db)
                            job_roles =job_role_table .select(where='job_id = {}'.format(orig_job_id))
                            if job_roles:
                                for job_role in job_roles:
                                    new_job_role = job_role_table.new()
                                    new_job_role.role_id = job_role.role_id
                                    new_job_role.job_id = job_rec.id
                                    job_role_table.save(new_job_role)
                                    
                        job_rec.start_date = dup_date + job_rec.start_date[10:]
                        job_rec.end_date = dup_date + job_rec.end_date[10:]
                        job_table.save(job_rec)
                
                        if move_assignments:
                            user_assignments = user_job_table.select(where="job_id = {}".format(orig_job_id))
                            if user_assignments:
                                for ua in user_assignments:
                                    orig_ua_id = ua.id # so we can refer to it later
                                    if action == "copy":
                                        ua.id=None
                                        
                                    ua.job_id = job_rec.id
                                    user_job_table.save(ua)
                                    if ua.id != orig_ua_id:
                                        ## TODO - We just gave the user a new assignment. Should let them know....
                                        pass
                                        
            elif action == "delete":
                event_table.delete(event_rec.id) #Jobs and usre_jobs should cascade delete
    
            else:
                # did not get a valid action?
                return "failure: Not a valid request"
                    
            g.db.commit()
            return 'success'
            
        except Exception as e:
            g.db.rollback()
            mes="Something went wrong while trying to manage that job."
            printException(mes,err=e)
            return "failure: {}".format(mes)
        
    return render_template('event_manage.html',rec=event_rec,new_date=new_date)
    
    
    
@mod.route('/delete/',methods=['GET','POST',])
@mod.route('/delete/<int:id>/',methods=['GET','POST',])
@table_access_required(Event)
def delete(id=0):
    setExits()
    return handle_delete(id)
    
def handle_delete(id):
    id = cleanRecordID(id)
    event = Event(g.db)
    if id <= 0:
        return abort(404)
        
    if id > 0:
        rec = event.get(id)
        
    if rec:
        event.delete(rec.id)
        g.db.commit()
    
    return redirect(g.listURL)
    
@mod.route('/delete_from_activity/',methods=['GET','POST',])
@mod.route('/delete_from_activity/<int:activity_id>/<int:id>/',methods=['GET','POST',])
def delete_from_activity(activity_id=-1,id=0):
    """Delete a record, but then return to the activity record
    Watch out! the params are swapped from usual
    """
    g.listURL = url_for('activity.edit') + str(cleanRecordID(activity_id))
    return handle_delete(id)
    
    
@mod.route('/send_event_email/',methods=['GET','POST',])
@mod.route('/send_event_email/<int:event_id>/',methods=['GET','POST',])
@table_access_required(Event)
def send_event_email(event_id):
    """Send a custom email to all or some the people who have signed up for an event"""
    
    event_id = cleanRecordID(event_id)
    event = Event(g.db).select_one(where="event.id = {}".format(event_id))
    if not event:
        return "failure: That is not a valid event record"
        
    include_calendar = request.form.get("include_calendar",True) # include the calenar attachments by default
    
    # import pdb;pdb.set_trace()
                    
    if request.form:
        valid_form = True
        if not request.form.get("message",'').strip():
            flash("You must include a message.")
            valid_form = False
        if not request.form.get("subject",'').strip():
            flash("You must include a subject.")
            valid_form = False
        if  not ('user' in request.form or 'user[]' in request.form):
            flash("You must select at least one recipient")
            valid_form = False
            
        # send emails
        if valid_form:
            include_calendar = "include_calendar" in request.form
            users = request.form.getlist('user[]') # multiple recipients selected
            if not users:
                users = request.form.getlist('user') # just a single user
                
            for user_id in users:
                user = User(g.db).get(cleanRecordID(user_id))
                if user:
                    # get jobs for this user
                    sql = """job.id in (
                    select job_id from user_job where user_id = {} and job_id in (
                        select job.id from job where job.event_id = {}
                        )
                    )
                    """.format(user.id,event_id)
                    job_list = get_job_rows(where=sql,is_admin=True)
                    if job_list:
                        # send_signup_email(job_data_list,user,template_path,bp,**kwargs)
                        send_signup_email(job_list,user,'email/event_notification.md',mod,
                        form=request.form,
                        subject=request.form["subject"],
                        event=event,
                        no_calendar = not include_calendar,
                        from_address = job_list[0].event_manager_email,
                        from_sender=f"{job_list[0].event_manager_first_name} {job_list[0].event_manager_last_name}",
                        )
                        
            return 'success'
            
    
    # Get the users who have signed up fo this event
    # import pdb;pdb.set_trace()
    
    sql = """select 
                user.*,
                job.title as job_title, 
                sum(user_job.positions) as positions, 
                job.start_date as job_start_date
            from user_job
            join user on user.id = user_job.user_id 
            join job on job.id = user_job.job_id
            where user_job.job_id in (select job.id from job where job.event_id = {event_id})
            group by user.id
            order by user.last_name, user.first_name, job_start_date
            """.format(event_id=event_id)
    users = User(g.db).query(sql)

    return render_template('event_email_form.html',
                event=event,
                users=users,
                form=request.form,
                include_calendar=include_calendar,
                )
    

def valid_input(rec):
    valid_data = True
    
    # # Require a default location
#     # No longer Requied as of 5/2021
#     if cleanRecordID(rec.location_id) < 1:
#         valid_data = False
#         flash("You must select a default location.")
        
    #Number Served and Tips received must be numbers
    if rec.number_served:
        n = Numeric(rec.number_served)
        if n.is_number:
            rec.number_served = n.int
        else:
            flash("Number Served must be a number (or empty)")
            valid_data = False
        
    if rec.tips_received:
        n = Numeric(rec.tips_received)
        if n.is_number:
            rec.tips_received = n.float
        else:
            flash("Tips Received must be a number (or empty)")
            valid_data = False
            
    form_datetime = request.form.get("contract_date",'')
    if form_datetime:
        temp_datetime = getDatetimeFromString(form_datetime)
        if temp_datetime == None:
            #Failed conversion
            valid_data = False
            flash("That is not a valid Contract date")

    #import pdb;pdb.set_trace()
    if rec.total_contract_price:
        n = Numeric(rec.total_contract_price)
        if n.is_number:
            rec.total_contract_price = n.float
            if rec.total_contract_price < 0:
                flash("Total Contract Price must be greater than zero. (or leave it empty)")
                valid_data = False
        else:
            flash("Total Contract Price must be a number (or empty)")
            valid_data = False
         
    if rec.per_event_contract_price:
        n = Numeric(rec.per_event_contract_price)
        if n.is_number:
            rec.per_event_contract_price = n.float
            if rec.per_event_contract_price < 0:
                flash("Event Contract Price must be greater than zero. (or leave it empty)")
                valid_data = False
        else:
            flash("Event Contract Price must be a number (or empty)")
            valid_data = False
            
    # validate and convert start and end dates to timezone aware date strings
    form_datetime = request.form.get("event_start_date",'')
    if not form_datetime:
        valid_data = False
        flash("Enter a Start time for the event")
    else:
        temp_datetime = getDatetimeFromString(form_datetime)
        if temp_datetime == None:
            #Failed conversion
            valid_data = False
            flash("That is not a valid Start date")
        else:
            rec.event_start_date = temp_datetime #store as date time
        
    form_datetime = request.form.get("event_end_date",'')
    if not form_datetime:
        valid_data = False
        flash("Enter an end time for the event")
    else:
        temp_datetime = getDatetimeFromString(form_datetime)
        if temp_datetime == None:
            #Failed conversion
            valid_data = False
            flash("That is not a valid End date")
        else:
            rec.event_end_date = temp_datetime #store as date time

    if valid_data:
        # if no service dates, use event dates instead
        # This needs to be the last test
        if request.form.get("service_start_date",'') + request.form.get("service_end_date",'') =='':
            rec.service_start_date = rec.event_start_date
            rec.service_start_date_label_id = rec.event_start_date_label_id
            rec.service_end_date = rec.event_end_date
            rec.service_end_date_label_id = rec.event_end_date_label_id
        else:
            form_datetime = request.form.get("service_start_date",'')
            if not form_datetime:
                valid_data = False
                flash("Enter an start time for the service")
            else:
                temp_datetime = getDatetimeFromString(form_datetime)
                if temp_datetime == None:
                    #Failed conversion
                    valid_data = False
                    flash("That is not a valid Start date")
                else:
                    rec.service_start_date = temp_datetime #store as date time
            form_datetime = request.form.get("service_end_date",'')
            if not form_datetime:
                valid_data = False
                flash("Enter an end time for the service")
            else:
                temp_datetime = getDatetimeFromString(form_datetime)
                if temp_datetime == None:
                    #Failed conversion
                    valid_data = False
                    flash("That is not a valid End date")
                else:
                    rec.service_end_date = temp_datetime #store as date time

    if cleanRecordID(rec.manager_user_id) < 1:
        valid_data = False
        flash("You must specify a manager for this event")
            
    return valid_data