-- The Georgia Medicaid license rule now checks what DCH 914.2.1 asks, so it says so.
UPDATE compliancerules SET description = 'Georgia Medicaid NEMT: every driver holds a current valid Georgia driver''s license, or is legally licensed by the bordering state they live in - Alabama, Florida, North Carolina, South Carolina or Tennessee (DCH 914.2.1). Read from the active license on file and the state of the driver''s address; a bordering state''s license with no address state on file waits for somebody to add it.'
 WHERE code = 'GA_NET_LICENSE' AND accountid IS NULL AND effectiveto IS NULL;
