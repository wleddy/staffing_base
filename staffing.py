from flask import g, url_for
from shotglass2 import shotglass
from staffing_base import models
from staffing_base.views import signup,activity,event,job,calendar,location,activity_type, \
    attendance, task, event_date_label, client, activity_group

def create_menus():
    # a header row must have the some permissions or higher than the items it heads
    #import pdb;pdb.set_trace()
    if not 'admin' in g:
        raise AttributeError("g.admin does not exist")

    g.admin.register(models.Job,url_for('signup.roster'),display_name='View Roster',top_level=True,minimum_rank_required=80,add_to_menu=True)
    g.admin.register(models.Activity,url_for('activity.display'),display_name='Staffing Admin',header_row=True,minimum_rank_required=500,roles=['admin','activity manager'])
    g.admin.register(models.Activity,url_for('activity.display'),display_name='Activities',minimum_rank_required=500,roles=['admin','activity manager'])
    g.admin.register(models.Event,url_for('event.display'),display_name='Events',add_to_menu=False,minimum_rank_required=500,roles=['admin','activity manager'])
    g.admin.register(models.Location,url_for('location.display'),display_name='Locations',minimum_rank_required=500,roles=['admin','activity manager'])
    g.admin.register(models.ActivityGroup,url_for('activity_group.display'),display_name='Activity Groups',minimum_rank_required=500,roles=['admin','activity manager'])
    g.admin.register(models.ActivityType,url_for('activity_type.display'),display_name='Activity Types',minimum_rank_required=500,roles=['admin','activity manager'])
    g.admin.register(models.EventDateLabel,url_for('event_date_label.display'),display_name='Date Labels',minimum_rank_required=500,roles=['admin','activity manager'])
    g.admin.register(models.Client,url_for('client.display'),display_name='Clients',minimum_rank_required=500,roles=['admin','activity manager'])
    g.admin.register(models.Attendance,url_for('attendance.display'),display_name='Attendance',minimum_rank_required=500,roles=['admin','activity manager'])
    g.admin.register(models.Task,url_for('task.display'),display_name='Ad Hoc Tasks',minimum_rank_required=500,roles=['admin',])
    g.admin.register(models.UserJob,url_for('attendance.display'),display_name='User Jobs',minimum_rank_required=500,roles=['admin','activity manager'],add_to_menu=False)


def initalize_tables(db):
    models.init_event_db(db)


def register_blueprints(app):
    app.register_blueprint(signup.mod)
    app.register_blueprint(activity.mod)
    app.register_blueprint(event.mod)
    app.register_blueprint(job.mod)
    app.register_blueprint(calendar.mod)
    app.register_blueprint(location.mod)
    app.register_blueprint(activity_type.mod)
    app.register_blueprint(attendance.mod)
    app.register_blueprint(task.mod)
    app.register_blueprint(event_date_label.mod)
    app.register_blueprint(client.mod)
    app.register_blueprint(activity_group.mod)
    shotglass.register_maps(app)