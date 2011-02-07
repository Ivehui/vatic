import turkic.database
import turkic.models
from sqlalchemy import Column, Integer, Float, String, Boolean, Text
from sqlalchemy import ForeignKey, Table
from sqlalchemy.orm import relationship, backref
import Image
import vision
import random

video_labels = Table("videos2labels", turkic.database.Base.metadata,
    Column("video_id", Integer, ForeignKey("videos.id")),
    Column("label_id", Integer, ForeignKey("labels.id")))

class Video(turkic.database.Base):
    __tablename__   = "videos"

    id              = Column(Integer, primary_key = True)
    slug            = Column(String(250), index = True)
    labels          = relationship("Label",
                                   secondary = video_labels,
                                   backref = "videos")
    width           = Column(Integer)
    height          = Column(Integer)
    totalframes     = Column(Integer)
    location        = Column(String(250))
    skip            = Column(Integer, default = 0, nullable = False)
    perobjectbonus  = Column(Float, default = 0)
    completionbonus = Column(Float, default = 0)
    trainwithid     = Column(Integer, ForeignKey(id))
    trainwith       = relationship("Video", remote_side = id)
    isfortraining   = Column(Boolean, default = False)

    def __getitem__(self, frame):
        path = Video.getframepath(frame, self.location)
        return Image.open(path)

    @classmethod
    def getframepath(cls, frame, base = None):
        l1 = frame / 10000
        l2 = frame / 100
        path = "{0}/{1}/{2}.jpg".format(l1, l2, frame)
        if base is not None:
            path = "{0}/{1}".format(base, path)
        return path

class Label(turkic.database.Base):
    __tablename__ = "labels"

    id = Column(Integer, primary_key = True)
    text = Column(String(250))

class Segment(turkic.database.Base):
    __tablename__ = "segments"

    id = Column(Integer, primary_key = True)
    videoid = Column(Integer, ForeignKey(Video.id))
    video = relationship(Video, cascade = "all", backref = "segments")
    start = Column(Integer)
    stop = Column(Integer)

class Job(turkic.models.HIT):
    __tablename__ = "jobs"
    __mapper_args__ = {"polymorphic_identity": "jobs"}

    id             = Column(Integer, ForeignKey(turkic.models.HIT.id),
                            primary_key = True)
    segmentid      = Column(Integer, ForeignKey(Segment.id))
    segment        = relationship(Segment, cascade = "all", backref = "jobs")
    trainingresult = Column(Boolean)

    def getpage(self):
        return "?id={0}".format(self.id)

    def markastraining(self):
        """
        Marks this job as the result of a training run. This will automatically
        swap this job over to the training video and produce a replacement.
        """
        replacement = Job(segment = self.segment, group = self.group)
        trainingjob = self.segment.video.trainwith.segments[0].jobs[0]
        self.segment = self.segment.video.trainwith.segments[0]
        self.group = self.segment.jobs[0].group
        return replacement, trainingjob

    def marktrainingresult(self, status):
        """
        Marks the training result of tho job.
        """
        self.trainingresult = status
        self.worker.verified = status
        if not self.worker.verified:
            self.worker.block()

    def __iter__(self):
        return self.paths

class Path(turkic.database.Base):
    __tablename__ = "paths"
    
    id = Column(Integer, primary_key = True)
    jobid = Column(Integer, ForeignKey(Job.id))
    job = relationship(Job, cascade = "all", backref = "paths")
    labelid = Column(Integer, ForeignKey(Label.id))
    label = relationship(Label, cascade = "none", backref = "paths")

    def getboxes(self):
        return [x.getbox() for x in self.boxes]

class Box(turkic.database.Base):
    __tablename__ = "boxes"

    id = Column(Integer, primary_key = True)
    pathid = Column(Integer, ForeignKey(Path.id))
    path = relationship(Path, cascade = "all", backref = "boxes")
    xtl = Column(Integer)
    ytl = Column(Integer)
    xbr = Column(Integer)
    ybr = Column(Integer)
    frame = Column(Integer)
    occluded = Column(Boolean, default = False)
    outside = Column(Boolean, default = False)

    def getbox(self):
        return vision.Box(self.xtl, self.ytl, self.xbr, self.ybr,
                          self.frame, self.outside, self.occluded)

class PerObjectBonus(turkic.models.BonusSchedule):
    __tablename__ = "per_object_bonuses"
    __mapper_args__ = {"polymorphic_identity": "per_object_bonuses"}

    id = Column(Integer, ForeignKey(turkic.models.BonusSchedule.id), 
        primary_key = True)
    amount = Column(Float, default = 0.0, nullable = False)

    def description(self):
        return (self.amount, "per object")

    def award(self, hit):
        paths = len(hit.job.paths)
        hit.awardbonus(paths * self.amount, "For {0} objects".format(paths))

class CompletionBonus(turkic.models.BonusSchedule):
    __tablename__ = "completion_bonuses"
    __mapper_args__ = {"polymorphic_identity": "completion_bonuses"}

    id = Column(Integer, ForeignKey(turkic.models.BonusSchedule.id),
        primary_key = True)
    amount = Column(Float, default = 0.0, nullable = False)

    def description(self):
        return (self.amount, "if complete")

    def award(self, hit):
        hit.awardbonus(self.amount, "For complete annotation.")
