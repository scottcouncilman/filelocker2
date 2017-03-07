# filelocker2
File sharing via web (http://filelocker2.sourceforge.net/)
# Shibbolizing Filelocker 2.6

This fork is our attempt to Shibbolize the Filelocker2 app. We based our approach on the WebSSO diffs found in the Sourceforge issues 
for Filelocker. We did not implement all of those changes since they appear to have been written for 2.4. We simply hunted for the 
code in the refactored 2.6 version and then applied the bare minimum to get us through the SAML authentication process.

In order to promote confidence and security, we're open to comments that can help us improve the security of this app with minimal 
intrusion into existing code.

We have a successful test environment working. Here is our configuration:

- Red Hat Enterprise Linux in a VM
- Apache 2.2.15
-  MySQL 5.1.73
- Shibd 2.6.0
- Filelocker2 v2.6

Our campus IDP provides us (the SP) with basic attributes upon a successful authentication. Apache sets these attributes as RequestHeaders. We then pull information into Filelocker2 where needed.
We did some of our initial development using a Docker container and setting up a workstation to act as a SP. 
Using http://testshib.org we were able to create a successful authentication flow and proceed into testing on a development VM.
