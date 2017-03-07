# filelocker2
File sharing via web (http://filelocker2.sourceforge.net/)
# Shibbolizing Filelocker 2.6 for UC Santa Cruz

This fork is a UC Santa Cruz attempt to Shibbolize the Filelocker2 app. We based our approach on the WebSSO diffs found in the Sourceforge issues for Filelocker. 

The WebSSO diffs were written against v2.4 of Filelocker. Our approach was to hunt for the same functions in the 2.6 branch and then applied the bare minimum number of changes to get us through the SAML authentication process. We used the base 2.6 to create our install and modified files from that point.

In order to promote confidence and security, we're open to comments that can help us improve the security of this app with minimal 
intrusion into existing code. We're running a series of security probes against our changes, the underlying code, OS and application layers.

We have a successful test environment working. Here is our configuration:

- Red Hat Enterprise Linux in a VM
- Apache 2.2.x
- MySQL 5.1.73
- Shibd 2.6.0
- Filelocker2 v2.6

Our campus IDP provides us (the SP) with basic attributes upon a successful authentication. Apache sets these attributes as RequestHeaders. We then pull information into Filelocker2 where needed.
We did some of our initial development using a Docker container and setting up a workstation to act as a SP. 
Using http://testshib.org we were able to create a successful authentication flow and proceed into testing on a development VM.

# Issues
[03-07-17] Since we can run an issue tracker on a forked project, I'm documenting an issue that came up today. We have been doing some updates to the Apache and other libraries. It's possible we made a change that I can't see in the code. In Filelocker.py we had been successfully allowing a NULL password to be used. This stopped working and we starting getting authentication errors stemming from a compare function. I tried a couple of changes with no success. I deleted myself from the DB, restored an older version of Filelocker.py with CAS code commented out and got things working again. This will need more research.