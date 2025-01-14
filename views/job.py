from flask import request, session, g, redirect, url_for, abort, \
     render_template, flash, Blueprint
from datetime import datetime
from shotglass2.users.admin import login_required, table_access_required
from shotglass2.users.models import Role, User
from shotglass2.takeabeltof.utils import render_markdown_for, printException, cleanRecordID
from shotglass2.takeabeltof.date_utils import date_to_string, getDatetimeFromString, local_datetime_now
from shotglass2.takeabeltof.mailer import email_admin
from shotglass2.shotglass import get_site_config, is_ajax_request
from staffing_base.models import Event, Location, Job, UserJob, JobRole
from staffing_base.views.announcements import send_signup_email
from staffing_base.views.signup import get_job_rows

mod = Blueprint('job',__name__, template_folder='templates/job', url_prefix='/job')


def setExits():
    g.listURL = url_for('.display')
    g.editURL = url_for('.edit')
    g.deleteURL = url_for('.delete')
    g.title = 'Jobs'


# @mod.route('/')
# @table_access_required(Job)
# def display():
#     setExits()
#     g.title="Event Job List"
#     recs = Job(g.db).select()
#
#     return render_template('job_list.html',recs=recs)

from shotglass2.takeabeltof.views import TableView
PRIMARY_TABLE = Job
# this handles table list and record delete
@mod.route('/<path:path>',methods=['GET','POST',])
@mod.route('/<path:path>/',methods=['GET','POST',])
@mod.route('/',methods=['GET','POST',])
@table_access_required(PRIMARY_TABLE)
def display(path=None):
    # import pdb;pdb.set_trace()
    setExits()

    view = TableView(PRIMARY_TABLE,g.db)
    # optionally specify the list fields
    view.list_fields = [
            {'name':'id','label':'ID','class':'w3-hide-small','search':True},
            {'name':'title',},
            {'name':'start_date','label':'Date','search':'date','type':'date'},
        ]

    return view.dispatch_request()

    
@mod.route('/roster',methods=['GET','POST'])
@mod.route('/roster/',methods=['GET','POST'])
@table_access_required(Job)
def roster():
    setExits()
    
    from staffing_base.views.signup import roster
    return roster()
    
    
@mod.route('/edit/',methods=['GET','POST',])
@mod.route('/edit/<int:id>/',methods=['GET','POST',])
@mod.route('/edit/<int:id>/<int:event_id>/',methods=['GET','POST',])
@table_access_required(Job)
def edit(id=0,event_id=0,edit_from_list=False):
    setExits()
    g.title = 'Edit Job Record'
    #import pdb;pdb.set_trace()
    
    locations = Location(g.db).select()
    slots_filled = 0
    users = None
    
    if id == 0 and request.form:
        id = request.form.get('id',0)
        event_id = request.form.get('event_id',0)
    
    id = cleanRecordID(id)
    event_id = cleanRecordID(event_id)
    job = Job(g.db)
    
    if id < 0:
        return abort(404)
        
    if id > 0:
        rec = job.get(id)
        if not rec:
            flash("{} Record Not Found".format(job.display_name))
            return redirect(g.listURL)
        event_id = rec.event_id
        #slots_filled = job.slots_filled(rec.id)
        
    else:
        rec = job.new()
        #set default dates
        event_rec = Event(g.db).get(event_id)
        temp_date = datetime.now().replace(minute=0,second=0)
        rec.start_date = temp_date
        rec.end_date = temp_date
        if event_rec.service_start_date:
            rec.start_date = getDatetimeFromString(event_rec.service_start_date)
        if event_rec.service_end_date:
            rec.end_date = getDatetimeFromString(event_rec.service_end_date)
            
        if 'last_job' in session:
            # restore the data from the last job edited
            rec.update(session['last_job'])
            
        rec.event_id = event_id
    
    current_event = Event(g.db).get(event_id)

    #import pdb;pdb.set_trace()
    
    roles = Role(g.db).select(where='name <> "admin" and name <> "super"')
    
    if request.form:
        job.update(rec,request.form)
        #rec.event_id = cleanRecordID(request.form.get("event_id"))
        if valid_input(rec):
            if cleanRecordID(rec.location_id) <= 0:
                rec.location_id = None
            
            job.save(rec)
            
            # create job_role records
            job_role_table = JobRole(g.db)
            job_role_table.query("delete from job_role where job_id = {}".format(rec.id))
            for role in skills_to_list():
                job_role_rec = job_role_table.new()
                job_role_rec.job_id = rec.id
                job_role_rec.role_id = int(role)
                job_role_table.save(job_role_rec)
                
            g.db.commit()
            session['last_job'] = rec._asdict()
            if edit_from_list:
                return 'success'
            return redirect(g.listURL)
            
    skills_list = skills_to_list() #Try to get them from the request form
    if not skills_list and id > 0:
        # get the skills from the job_role table
        job_role_recs = JobRole(g.db).select(where="job_id = {}".format(id))
        if job_role_recs:
            skills_list = [x.role_id for x in job_role_recs]
                        
    template = 'job_edit.html'
    if edit_from_list:
        template = 'job_embed_edit.html'
    
    return render_template(template,rec=rec,
            roles=roles,
            current_event=current_event,
            locations=locations,
            slots_filled=slots_filled,
            users=users,
            skills_list=skills_list,
            )
    
    return render_template(template,rec=rec,
            roles=roles,
            current_event=current_event,
            locations=locations,
            slots_filled=slots_filled,
            users=users,
            skills_list=skills_list,
            )
            
                
@mod.route('/delete/',methods=['GET','POST',])
@mod.route('/delete/<int:id>/',methods=['GET','POST',])
@table_access_required(Job)
def delete(id=0):
    setExits()
    id = cleanRecordID(id)
    job = Job(g.db)
    if id <= 0:
        return abort(404)
        
    rec = job.get(id)
        
    if rec:
        ## Don't delete if there are any assignmehnts
        UJ = UserJob(g.db).select(where='job_id = {}'.format(id))
        if UJ:
            mes = "There are one or more users assigned to this job. You must remove the assignments first."
            if is_ajax_request():
                #this is an ajax request
                return "failure: " + mes
            else:
                flash(mes)
                return redirect(g.listURL)
            
        job.delete(rec.id)
        g.db.commit()
        if is_ajax_request():
            return "success"

    else:
        mes = "That record could not be found"
        if is_ajax_request():
            return f"failure: {mes}"
                
        flash(mes)
    
    return redirect(g.listURL)
    
    
@mod.route('/edit_job_from_list/<int:id>/',methods=['GET','POST',])
@mod.route('/edit_job_from_list/<int:id>',methods=['GET','POST',])
@mod.route('/edit_job_from_list/<int:id>/<int:event_id>/',methods=['GET','POST',])
@mod.route('/edit_job_from_list/<int:id>/<int:event_id>',methods=['GET','POST',])
@mod.route('/edit_job_from_list/',methods=['GET','POST',])
@table_access_required(Job)
def edit_job_from_list(id=0,event_id=0):
    return edit(id,event_id,True)
    
@mod.route('/delete_from_list/<int:id>/',methods=['GET','POST',])
@mod.route('/delete_from_list/<int:id>',methods=['GET','POST',])
@mod.route('/delete_from_list/',methods=['GET','POST',])
@table_access_required(Job)
def delete_from_list(id=0):
    id = cleanRecordID(id)
    if id > 0:
        rec = Job(g.db).get(id)
        if rec:
           return delete(id)
    return 'failure: Could not find a Job with that ID'

    
@mod.route('/get_job_list_for_event/',methods=['GET','POST',])
@mod.route('/get_job_list_for_event/<int:id>/',methods=['GET','POST',])
@mod.route('/get_job_list_for_event/<int:id>',methods=['GET','POST',])
def get_job_list_for_event(id=0):
    """Return a fully formated html table for use in the Event edit form"""
    #import pdb;pdb.set_trace()
    id = cleanRecordID(id)
    #jobs = Job(g.db).select(where='event_id = {}'.format(id))
    job_data = get_job_rows(None,None,"job.event_id = {}".format(id),[],is_admin=True,event_status_where='')
    
    return render_template('job_embed_list.html',jobs=job_data,event_id=id)
    
    
@mod.route('/manage/<int:id>/',methods=['GET','POST',])
@mod.route('/manage/<int:id>',methods=['GET','POST',])
@mod.route('/manage/',methods=['GET','POST',])
@table_access_required(Job)
def manage_job_set(id=None):
    """Duplicate, move or delete a set of jobs that share an event id and date"""
    
    #import pdb;pdb.set_trace()
    action = request.args.get('action')
    new_date=request.form.get('new_date','')
    
    id = cleanRecordID(request.form.get('id',id))
    
    if id < 1:
        return 'failure: That is not a valid job ID'
        
    if action not in [None,'copy','move','delete',]:
        return 'failure: That is not a valid action request'
    
    job = Job(g.db)
    rec = job.get(id)
    if not rec:
        return "failure: Job not found."
        
    dup_date = None
    if request.form and action != 'delete':
        # validate the new date for a set
        try:
            dup_date = coerce_datetime(request.form.get('new_date',''),'23:00:00')
            if dup_date:
                # You can't move a set into the past
                if dup_date < local_datetime_now():
                    return "failure: You can't move or copy a set into the past"
                    
                #convert it to a string
                dup_date = date_to_string(dup_date,'iso_date') #'YYYY-MM-DD'
            
                ## if there is already a job for this event on that date, don't move or copy
                sql = """select user_job.id, job.event_id, job.start_date from user_job
                        join job on user_job.job_id = job.id
                        where job.event_id = {} and 
                        date(job.start_date,'localtime') = date('{}')""".format(rec.event_id,dup_date)
                UJ = UserJob(g.db).query(sql)
                if UJ:
                    return "failure: There are already jobs on that date. You can't move or copy to there."
                
            else:
                return "failure: That is not a valid date"
        except:
            return "failure: Got an error while processing the date"
            
    if request.form and (dup_date or action == 'delete'):
        recs = job.select(where="event_id = {} and date(start_date,'localtime') = date('{}','localtime')".format(rec.event_id,rec.start_date))
        if recs:
            for rec in recs:
                if action == 'delete':
                    ## Don't delete if there are any assignmehnts
                    UJ = UserJob(g.db).select(where='job_id = {}'.format(rec.id))
                    if UJ:
                        g.db.rollback()
                        return "failure: There are one or more users assigned to this job. You must remove the assignments first."
                        
                    job.delete(rec.id)
                else:
                    ## copy or move
                    if action == 'copy':
                        rec.id = None
                        
                    rec.start_date = dup_date + rec.start_date[10:]
                    rec.end_date = dup_date + rec.end_date[10:]
                    job.save(rec)
    
            job.commit()

            return 'success'
        
    return render_template('job_manage.html',rec=rec,new_date=new_date)
    
    
@mod.route('/assignment_manager/<int:job_id>',methods=['GET',])
@mod.route('/assignment_manager/<int:job_id>/',methods=['GET',])
@mod.route('/assignment_manager',methods=['POST',])
@mod.route('/assignment_manager/',methods=['POST',])
@table_access_required(Job)
def assignment_manager(job_id=0):
    """Add or remove a signup initiated by a manager
    Comes from a modal dialog but unlike most times, this method will not close
    the dialog on "success". The Dlog remains open until the user cancels it."""
    
    setExits()
    site_config = get_site_config()
    job=None
    signup = None
    assigned_users = None
    filled_positions = None
    
    #import pdb;pdb.set_trace()

    #Get the job id
    if not job_id and request.form:
        job_id = request.form.get('id',None)
    
    # Sanatize job_id
    job_id = cleanRecordID(job_id)
    if job_id < 1:
        return "failure: That is not a valid job id"
        
    #if Post, create assignment
    if request.form:
        assignment_user_id = cleanRecordID(request.form.get('assignment_user_id',None))
        if assignment_user_id < 1:
            return "failure: You need to select a user first."
            
        if cleanRecordID(request.form.get('positions')) < 1:
            return "failure: The number of positions must be at least 1."
            
        signup = UserJob(g.db).select_one(where='user_id = {} and job_id = {}'.format(assignment_user_id,job_id))
        if not signup:
            signup = UserJob(g.db).new()
            signup.user_id = assignment_user_id
            signup.job_id = job_id
        
        UserJob(g.db).update(signup,request.form)
        signup.modified = local_datetime_now()
        UserJob(g.db).save(signup)
        g.db.commit()
        
        # Only send a notification if the job is in the future
        assigned_job = Job(g.db).get(job_id)
        if assigned_job and getDatetimeFromString(assigned_job.start_date) > local_datetime_now():
            # send a special email to the user to inform them of the assignment.
            manager_rec = User(g.db).get(session.get('user_id',0))
            user_rec = User(g.db).get(assignment_user_id)
            # need a fresh copy of this
            job_data = get_job_rows(None,None,"job.id = {}".format(job_id),[],is_admin=True,event_status_where='')
            if job_data:
                job_data = job_data[0]
                subject = "{} {} has given you an assignment".format(manager_rec.first_name,manager_rec.last_name)
                send_signup_email(job_data,user_rec,'email/inform_user_of_assignment.html',mod,manager=manager_rec,subject=subject,job_data=job_data,escape=False)
            else:
                # failed to get the job data... this should never happen
                email_admin(subject="Alert from {}".format(site_config['SITE_NAME']),
                    message="Unable to send Manager Assignment email. 'job_data' is None? 'job_id' = {}, 'user_id'={}".format(job_id,assignment_user_id))
                flash("Unable to send email to user. (Err: job_data is None)")
        # The form is going to be redisplayed so clear the signup record
        signup = None

    if not signup:
        signup = UserJob(g.db).new()
        signup.job_id = job_id
        signup.positions=0
        
    #Get the job to display
    job_data = get_job_rows(None,None,"job.id = {}".format(job_id),[],is_admin=True,event_status_where='')
    job_data = job_data[0] if job_data else None
    
    # 4/15/19 - let manager assign anyone they like. Show all users
    all_users = User(g.db).select()
 
    #get all users currently assigned
    assigned_users = UserJob(g.db).get_assigned_users(job_id)

    #remove users already assigned from skilled users
    if assigned_users:
        for au in assigned_users:
            if all_users:
                for i in range(len(all_users)):
                    if all_users[i].id == au.id:
                        del all_users[i]
                        break
    return render_template('assignment_manager.html',
            job=job_data,
            signup=signup,
            assigned_users=assigned_users,
            all_users=all_users,
            )

    
@mod.route('/assignment_manager_delete/<int:job_id>/<int:user_id>',methods=['GET',])
@mod.route('/assignment_manager_delete/<int:job_id>/<int:user_id>/',methods=['GET',])
@mod.route('/assignment_manager_delete/',methods=['GET',])
@table_access_required(Job)
def assignment_manager_delete(job_id=0,user_id=0):
    """Delete a job assignment"""
    setExits()
    site_config = get_site_config()
    assigned_job = None
    
    #import pdb;pdb.set_trace()
    job_id = cleanRecordID(job_id)
    user_id = cleanRecordID(user_id)
    if job_id > 0 and user_id > 0:
        assigned_job = Job(g.db).get(job_id) # need this later
        
        signup=UserJob(g.db).select_one(where='job_id = {} and user_id = {}'.format(job_id,user_id))
        if signup:
            UserJob(g.db).delete(signup.id)
            g.db.commit()

            # Only send a notification if the job is in the future
            #assigned_job = Job(g.db).get(job_id)
            if assigned_job and getDatetimeFromString(assigned_job.start_date) > local_datetime_now():
                job_data = get_job_rows(None,None,"job.id = {}".format(job_id),[],is_admin=True,event_status_where='')
                if job_data:
                    job_data = job_data[0]
                    # send a special email to the user to inform them of the assignment.
                    manager_rec = User(g.db).get(session.get('user_id',0))
                    user_rec = User(g.db).get(user_id)
                    subject = "{} {} has cancelled your assignment".format(manager_rec.first_name,manager_rec.last_name)
                    send_signup_email(job_data,user_rec,'email/inform_user_of_cancellation.html',mod,manager=manager_rec,subject=subject,job_data=job_data,no_calendar=True)
                else:
                    # failed to get the job data... this should never happen
                    email_admin(subject="Alert from {}".format(site_config['SITE_NAME']),
                        message="Unable to send Manager Cancellation email. 'job_data' is None? 'job_id' = {}, 'user_id'={}".format(job_id,user_id))
                    flash("Unable to send email to user. (Err: job_data is None)")

            return assignment_manager(job_id)
            
        return "failure: User_Job record could not be found"
            
    return "failure: Invalid User or Job id"

@mod.route('/assignment_manager_done/<int:event_id>',methods=['GET',])
@mod.route('/assignment_manager_done/<int:event_id>/',methods=['GET',])
@mod.route('/assignment_manager_done',methods=['POST',])
@mod.route('/assignment_manager_done/',methods=['POST',])
@table_access_required(Job)
def assignment_manager_done(event_id=0):
    """Simply return 'success' to allow modal assignment dialog to close"""
    return 'success'

def valid_input(rec):
    valid_data = True
    #import pdb;pdb.set_trace()
    
    job_title = request.form.get('title','').strip()
    if not job_title:
        valid_data = False
        flash("You must give the job a title")
        
    if not rec.event_id or int(rec.event_id) < 1:
        valid_data = False
        flash("You must select an event for this job")
    else:
        event_rec = Event(g.db).get(rec.event_id)
        if not event_rec:
            valid_data = False
            flash("That does not seem to be a valid Event ID")
            
    job_date = getDatetimeFromString(request.form.get("start_date",""))
    if not job_date:
        valid_data = False
        flash("That is not a valid starting time")
    else:
        rec.start_date = job_date
    job_date = getDatetimeFromString(request.form.get("end_date",""))
    if not job_date:
        valid_data = False
        flash("That is not a valid ending time")
    else:
        rec.end_date = job_date
    #coerce the start and end datetimes
    #Get the start time into 24 hour format
    # tempDatetime =coerce_datetime(request.form.get("job_date",""),request.form.get('start_time',''),request.form['start_time_AMPM'])
#     if not tempDatetime:
#         valid_data = False
#         flash("Start Date and Start Time are not valid")
#     else:
            
    # tempDatetime =coerce_datetime(request.form.get("job_date",""),request.form.get('end_time',''),request.form['end_time_AMPM'])
    # if not tempDatetime:
    #     valid_data = False
    #     flash("End Date and End Time are not valid")
    # else:
    #     rec.end_date = tempDatetime
        

    # ensure that both fields are the same type before comparing
    if type(rec.start_date) == type(rec.end_date) and rec.start_date > rec.end_date:
        valid_data = False
        flash("The End Time can't be before the Start Time")
        
    if not rec.max_positions or int(rec.max_positions) < 1:
        valid_data = False
        flash("The number of People Requested must be greater than 0")
        
    if not skills_to_list():
        valid_data = False
        flash("You must select at least one Skill for the job.")

    return valid_data
    
    
def coerce_datetime(date_str,time_str,ampm=None):
    """Convert a string date and a string time into a datetime object
    if ampm is None, assume 24 hour time else 12 hour"""
    #import pdb;pdb.set_trace()
    try:
        tempDatetime = None
        time_parts = time_str.split(":")
        if len(time_parts) == 0 or time_parts[0] == '':
            valid_data = False
            flash("That is not a valid time")
        else:
            for key in range(len(time_parts)):
                if len(time_parts[key]) == 1:
                    time_parts[key] = "0" + time_parts[key]
                    
            time_parts.extend(["00","00"])
            if ampm != None:
                if ampm.upper() == 'PM' and int(time_parts[0])<12:
                    time_parts[0] = str(int(time_parts[0]) + 12)            
                if ampm.upper() == 'AM' and int(time_parts[0])> 12:
                    time_parts[0] = str(int(time_parts[0]) - 12)            
            time_str = ":".join(time_parts[:3])
            tempDatetime = getDatetimeFromString("{} {}".format(date_str,time_str))
        
        return tempDatetime
    except Exception as e:
        mes = "Error in job.coerce_datetime"
        flash(printException(mes,level='error',err=e))
        return None
        
    
def skills_to_list():
    """Create a list of skill (role) ids from form"""
    skills = []
    for role_id in request.form.getlist('skills'):
        skills.append(role_id)
    if not skills:
        # This is a hack that has to do with the way I submit the form via js
        # The 'skills' elements in request.form have the name 'skills[]' only when submitted
        #   via common.js.submitModalForm. Don't want to change it because it works elsewhere.
        # This may be an artifact of the way php handles multiple select elements
        for role_id in request.form.getlist('skills[]'):
            skills.append(role_id)
        
    
    return skills
    