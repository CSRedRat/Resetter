#!/usr/bin/python
import apt
import apt.package
import logging
import os
import subprocess
import sys
import time
from PyQt4 import QtCore, QtGui
from AptProgress import UIAcquireProgress, UIInstallProgress
from Account import AccountDialog
import apt_pkg


class ProgressThread(QtCore.QThread):
    def __init__(self, file_in):
        QtCore.QThread.__init__(self)
        self.op_progress = None
        self._cache = apt.Cache(self.op_progress)
        self._cache.open()
        self.file_in = file_in
        self.isDone = False
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        handler = logging.FileHandler('/var/log/resetter/resetter.log')
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        QtGui.qApp.processEvents()
        apt_pkg.init()

    def file_len(self):
        try:
            p = subprocess.Popen(['wc', '-l', self.file_in], stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            result, err = p.communicate()
            return int(result.strip().split()[0])
        except subprocess.CalledProcessError:
            pass

    def run(self):
        print self.file_len()
        if self.file_len() != 0:
            print("removing packages")
            loading = 0
            x = float(100) / self.file_len()
            with open(self.file_in) as packages:
                    for pkg_name in packages:
                        try:
                            loading += x
                            self.pkg = self._cache[pkg_name.strip()]
                            self.pkg.mark_delete(True, purge=True)
                            print "{} will be removed".format(self.pkg)
                            self.emit(QtCore.SIGNAL('updateProgressBar(int, bool)'), loading, self.isDone)
                        except KeyError as error:
                            self.logger.error("{}".format(error))
                            continue
                    print "Done reading"
                    self.isDone = True
                    self.emit(QtCore.SIGNAL('updateProgressBar(int, bool)'), 100, self.isDone)
        else:
            self.isDone = True
            print "All removable packages are already removed"
            self.emit(QtCore.SIGNAL('updateProgressBar(int, bool)'), 100, self.isDone)



class Apply(QtGui.QDialog):

    def __init__(self, file_in, response, parent=None):
        super(Apply, self).__init__(parent)
        self.setMinimumSize(400, 250)
        self.file_in = file_in
        self.response = response
        self.setWindowTitle("Applying")
        self.error_msg = QtGui.QMessageBox()
        self.error_msg.setIcon(QtGui.QMessageBox.Critical)
        self.error_msg.setWindowTitle("Error")
        self.buttonCancel = QtGui.QPushButton()
        self.buttonCancel.setText("Cancel")
        self.buttonCancel.clicked.connect(self.cancel)
        self.progress = QtGui.QProgressBar(self)
        self.lbl1 = QtGui.QLabel()
        gif = os.path.abspath("/usr/lib/resetter/data/icons/chassingarrows.gif")
        self.movie = QtGui.QMovie(gif)
        self.movie.setScaledSize(QtCore.QSize(20, 20))
        self.pixmap = QtGui.QPixmap("/usr/lib/resetter/data/icons/checkmark.png")
        self.pixmap2 = self.pixmap.scaled(20, 20)
        verticalLayout = QtGui.QVBoxLayout(self)
        verticalLayout.addWidget(self.lbl1)
        verticalLayout.addWidget(self.progress)
        gridLayout = QtGui.QGridLayout()
        self.labels = {}
        for i in range(1, 6):
            for j in range(1, 3):
                self.labels[(i, j)] = QtGui.QLabel()
                self.labels[(i, j)].setMinimumHeight(20)
                gridLayout.addWidget(self.labels[(i, j)], i, j)
        gridLayout.setAlignment(QtCore.Qt.AlignCenter)
        self.labels[(1,2)].setText("Loading Apps")
        self.labels[(2,2)].setText("Removing Apps")
        self.labels[(3,2)].setText("Deleting Users")
        self.labels[(4,2)].setText("Cleaning Up")
        if self.response:
            self.labels[(5,2)].setText("Removing old kernels")
        verticalLayout.addSpacing(20)
        verticalLayout.addLayout(gridLayout)
        verticalLayout.addWidget(self.buttonCancel, 0, QtCore.Qt.AlignRight)
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        handler = logging.FileHandler('/var/log/resetter/resetter.log')
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.progressView = ProgressThread(self.file_in)
        self.account = AccountDialog(self)
        self.connect(self.progressView, QtCore.SIGNAL("updateProgressBar(int, bool)"), self.updateProgressBar)
        self._cache = self.progressView._cache
        self.aprogress = UIAcquireProgress(self.progress, self.lbl1)
        self.iprogress = UIInstallProgress(self.progress, self.lbl1)
        self.addUser()

    def updateProgressBar(self, percent, isdone):
        self.lbl1.setText("Loading Package List")
        self.progress.setValue(percent)
        self.labels[(1,1)].setMovie(self.movie)

        self.movie.start()
        if isdone:
            self.labels[(1, 1)].setPixmap(self.pixmap2)
            self.movie.stop()
            self.labels[(2, 1)].setMovie(self.movie)
            self.movie.start()
            self.remove()

    def cancel(self):
        self.logger.warning("Progress thread was cancelled")
        self.progressView.terminate()
        self.close()

    def remove(self):
        print "removing"
        self.logger.info("Removing Programs")
        try:
            dep_list = "deplist"
            with open(dep_list, "w") as dl:
                for self.pkg in self._cache.get_changes():
                    if self.pkg != self.pkg.name:
                        dl.write('{}\n'.format(self.pkg))
            self.getDependencies()
            self.logger.info("Keep Count before commit: {}".format(self._cache.keep_count))
            self.logger.info("Delete Count before commit: {}".format(self._cache.delete_count))
            self._cache.commit(self.aprogress, self.iprogress)
            self.logger.info("Broken Count after commit: {}".format(self._cache.broken_count))
            self.movie.stop()
            self.labels[(2, 1)].setPixmap(self.pixmap2)
            self.progress.setValue(int(100))
            self.removeUsers()
            self.fixBroken()
        except Exception as arg:
            self.movie.stop()
            self.logger.error("Sorry, package removal failed [{}]".format(str(arg)))
            self.error_msg.setText("Something went wrong... please check details")
            self.error_msg.setDetailedText("Package removal failed [{}]".format(str(arg)))
            self.error_msg.exec_()

    def fixBroken(self):
        self.lbl1.setText("Cleaning up...")
        self.logger.info("Cleaning up..." )
        self.labels[(4,1)].setMovie(self.movie)

        self.movie.start()
        self.setCursor(QtCore.Qt.BusyCursor)
        self.process = QtCore.QProcess()
        self.process.finished.connect(self.onFinished)
        self.process.start('bash', ['/usr/lib/resetter/data/scripts/fix-broken.sh'])

    def onFinished(self, exit_code, exit_status):
        if exit_code or exit_status != 0:
            self.logger.error("fixBroken() finished with exit code: {} and exit_status {}."
                              .format(exit_code, exit_status))
        else:
            self.logger.debug("Cleanup finished with exit code: {} and exit_status {}.".format(exit_code, exit_status))
            self.movie.stop()
            self.labels[(4, 1)].setPixmap(self.pixmap2)
            self.unsetCursor()
            self.lbl1.setText("Done fixing")
            self.removeOldKernels(self.response)

    def removeOldKernels(self, response):
        if response:
            self.logger.info("Starting kernel removal...")
            self.labels[(5, 1)].setMovie(self.movie)
            self.movie.start()
            self.setCursor(QtCore.Qt.BusyCursor)
            self._cache.clear()
            self.progress.setValue(0)
            try:
                with open("Kernels","r") as kernels:
                    for kernel in kernels:
                        pkg = self._cache[kernel.strip()]
                        if pkg.is_installed:
                            pkg.mark_delete(True, purge=True)
                self.logger.info("Removing old kernels...")
                self._cache.commit(self.aprogress, self.iprogress)
                self.progress.setValue(100)
                self.labels[(5, 1)].setPixmap(self.pixmap2)
                self.unsetCursor()
                self.lbl1.setText("Finished")
            except Exception, arg:
                self.logger.error("Kernel removal failed [{}]".format(str(arg)))
                print "Sorry, kernel removal failed [{}]".format(str(arg))
            self.showUserInfo()
        else:
            self.lbl1.setText("Finished")
            self.showUserInfo()
            self.logger.info("Old kernel removal option not chosen")

    def start(self):
        self.progressView.start()

    def removeUsers(self):
        self.logger.info("Starting user removal")
        self.labels[(3, 1)].setMovie(self.movie)
        self.movie.start()
        try:
            subprocess.Popen(['bash', 'custom-users-to-delete.sh'], stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
            self.logger.debug("user removal completed successfully: [{}]".format(subprocess.STDOUT))
        except subprocess.CalledProcessError, e:
            self.logger.error("unable removing user [{}]".format(e.output))
        self.movie.stop()
        self.labels[(3, 1)].setPixmap(self.pixmap2)

    def getDependencies(self):
        try:
            self.setCursor(QtCore.Qt.WaitCursor)
            cmd = subprocess.Popen(['grep', '-vxf', self.file_in, 'deplist'],
                                   stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
            cmd.wait()
            result = cmd.stdout
            self.unsetCursor()
            with open("keep", "w") as output:
                for l in result:
                    try:
                        self.pkg = self._cache[l.strip()]
                        self.pkg.mark_keep()
                        output.writelines(l)
                    except KeyError as ke:
                        self.logger.error("{}".format(ke))
                        continue
        except subprocess.CalledProcessError as e:
            print "error: {}".format(e.output)
            self.logger.error("getting Dependencies failed: {}".format(e.output))

    def addUser(self):
        choice = QtGui.QMessageBox.question\
            (self, 'Would you like set your new account?',
             "Set your own account? Click 'No' so that I can create a default account for you instead",
             QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)
        if choice == QtGui.QMessageBox.Yes:
            self.show()
            self.account.exec_()
            self.start()
            self.showMinimized()
            print "Adding custom user"

        if choice == QtGui.QMessageBox.No:
            print "Adding default user"
            try:
                p = subprocess.Popen(['bash', '/usr/lib/resetter/data/scripts/new-user.sh'], stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
                self.logger.info("Default user added")
                p.wait()
                self.start()
            except subprocess.CalledProcessError as e:
                self.logger.error("unable to add default user [{}]".format(e.output), exc_info=True)
                print e.output

    def rebootMessage(self):
        choice = QtGui.QMessageBox.information \
            (self, 'Please reboot to complete system changes',
             "Reboot now?",
             QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)
        if choice == QtGui.QMessageBox.Yes:
            self.logger.info("system rebooted after package removals")
            os.system('reboot')
        else:
            self.logger.info("reboot was delayed.")

    def showUserInfo(self):
        msg = QtGui.QMessageBox(self)
        msg.setWindowTitle("User Credentials")
        msg.setIcon(QtGui.QMessageBox.Information)
        msg.setText("Please use these credentials the next time you log-in")
        msg.setInformativeText("USERNAME: <b>{}</b><br/> PASSWORD: <b>{}</b>".format(self.account.getUser(), self.account.getPassword()))
        msg.setDetailedText("If you deleted your old user account, "
                            "this account will be the only local user on your system")
        msg.exec_()
        self.logger.info("Credential message info shown")
        self.rebootMessage()
