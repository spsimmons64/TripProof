-- ################################################################################################
-- # 358 - wheelchair securement training is asked of the driver of a wheelchair vehicle.
-- #
-- # It was asked of every driver of a company with any wheelchair vehicle, so on a trip it refused
-- # a driver taking an ambulatory passenger in a sedan (MODIVTEST CF-4). 49 CFR 37.173 trains to
-- # the duties performed. driver.wheelchairvehicle is the fleet's answer on the driver's own file
-- # (any of them may be put in the van) and the vehicle's own on a trip. Passenger assistance
-- # training is untouched: helping a passenger with a disability is every driver's duty.
-- ################################################################################################

UPDATE compliancerules SET applieswhen = '{"fact":"driver.wheelchairvehicle","is":true}'
 WHERE code = 'SECUREMENT_TRAINING_CERT' AND accountid IS NULL AND effectiveto IS NULL;
