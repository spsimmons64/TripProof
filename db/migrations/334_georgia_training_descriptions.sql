-- ################################################################################################
-- # 334 - the Georgia driver trainings each say what they are.
-- #
-- # 318 and 321 copied the first aid description onto the safety and sensitivity and spill kit
-- # rules, and the general defensive driving description - "not required by any regulation" - onto
-- # the Georgia ones that are required. Each now says what the source asks for.
-- #
-- # DCH NEMT Part II (October 2026) 916.1: driver training, first aid, and spill kit and biohazard
-- # removal training before driving under the NEMT program, with the certifications maintained for
-- # the driver's whole agreement with the broker; driver training includes a passenger assistance
-- # orientation (916.1.1), an ongoing safety and sensitivity program (916.1.2) and defensive driving
-- # (916.1.3). 916.2: a driver who has not completed it has ninety days from assignment.
-- ################################################################################################

UPDATE compliancerules SET description = 'Georgia Medicaid NEMT requires every driver to complete first aid training before driving under the program, and to keep the certification current for as long as they drive for the broker (DCH 916.1). A driver who has not had it has ninety days from assignment (916.2). The card carries its own expiry, which is what TripProof tracks.'
 WHERE code = 'GA_NET_FIRST_AID' AND accountid IS NULL AND effectiveto IS NULL;

UPDATE compliancerules SET description = 'Georgia Medicaid NEMT requires driver training to include an ongoing safety and sensitivity program, so that drivers keep a safe operating environment for the people they carry (DCH 916.1.2). A driver who has not had it has ninety days from assignment (916.2).'
 WHERE code = 'GA_NET_SAFETY_SENSITIVITY' AND accountid IS NULL AND effectiveto IS NULL;

UPDATE compliancerules SET description = 'Georgia Medicaid NEMT requires every driver to be trained in using a spill kit and removing biohazards before driving under the program, and to keep the certification current for as long as they drive for the broker (DCH 916.1). A driver who has not had it has ninety days from assignment (916.2).'
 WHERE code = 'GA_NET_SPILL_KIT' AND accountid IS NULL AND effectiveto IS NULL;

UPDATE compliancerules SET description = 'Georgia Medicaid NEMT requires driver training before driving under the program, and that training must include defensive driving (DCH 916.1 and 916.1.3). The certification is kept current for as long as the driver drives for the broker; a driver who has not had it has ninety days from assignment (916.2).'
 WHERE code = 'GA_NET_DRIVER_TRAINING' AND accountid IS NULL AND effectiveto IS NULL;

UPDATE compliancerules SET description = 'Georgia DHS coordinated transportation requires drivers to complete safety, courtesy and sensitivity awareness training, kept in the driver qualification file (DHS MAN1425, Chapter 2, Driver Training).'
 WHERE code = 'DHS_SAFETY_SENSITIVITY' AND accountid IS NULL AND effectiveto IS NULL;

UPDATE compliancerules SET description = 'Georgia DHS coordinated transportation requires drivers to complete a certified defensive driving course (DHS MAN1425, Chapter 2, Driver Training).'
 WHERE code = 'DHS_DEFENSIVE' AND accountid IS NULL AND effectiveto IS NULL;

UPDATE compliancerules SET description = 'Georgia DHS coordinated transportation requires drivers to hold a current basic first aid certification (DHS MAN1425, Chapter 2, Driver Training). The card carries its own expiry, which is what TripProof tracks.'
 WHERE code = 'DHS_FIRST_AID' AND accountid IS NULL AND effectiveto IS NULL;
